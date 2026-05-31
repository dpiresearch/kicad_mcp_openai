/**
 * Visual design snapshot tools for schematic and PCB review.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { mkdir, readdir, writeFile } from "fs/promises";
import { existsSync } from "fs";
import { basename, dirname, extname, join, resolve } from "path";
import { z } from "zod";
import { logger } from "../logger.js";

type CommandFunction = (command: string, params: Record<string, unknown>) => Promise<any>;

type ResolvedDesignPaths = {
  projectDir: string;
  pcbPath?: string;
  schematicPath?: string;
};

function safeLabel(label?: string): string {
  const cleaned = (label || "visual-check").trim().replace(/[^a-zA-Z0-9._-]+/g, "_");
  return cleaned || "visual-check";
}

function timestamp(): string {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function findFirstFile(dir: string, extension: string, preferredStem?: string): Promise<string | undefined> {
  if (!existsSync(dir)) return undefined;
  const entries = await readdir(dir);
  if (preferredStem) {
    const preferred = entries.find((entry) => entry === `${preferredStem}${extension}`);
    if (preferred) return join(dir, preferred);
  }
  const match = entries.find((entry) => entry.endsWith(extension));
  return match ? join(dir, match) : undefined;
}

async function resolveDesignPaths(
  callKicadScript: CommandFunction,
  projectPath?: string,
  pcbPath?: string,
  schematicPath?: string,
): Promise<ResolvedDesignPaths> {
  let resolvedPcb = pcbPath ? resolve(pcbPath) : undefined;
  let resolvedSchematic = schematicPath ? resolve(schematicPath) : undefined;
  let projectDir = resolvedPcb ? dirname(resolvedPcb) : resolvedSchematic ? dirname(resolvedSchematic) : undefined;
  let projectStem = resolvedPcb ? basename(resolvedPcb, extname(resolvedPcb)) : undefined;

  if (projectPath) {
    const resolvedProject = resolve(projectPath);
    const projectExt = extname(resolvedProject);
    if (projectExt === ".kicad_pcb") {
      resolvedPcb = resolvedPcb || resolvedProject;
      projectDir = dirname(resolvedProject);
      projectStem = basename(resolvedProject, projectExt);
    } else if (projectExt === ".kicad_sch") {
      resolvedSchematic = resolvedSchematic || resolvedProject;
      projectDir = dirname(resolvedProject);
      projectStem = basename(resolvedProject, projectExt);
    } else if (projectExt === ".kicad_pro") {
      projectDir = dirname(resolvedProject);
      projectStem = basename(resolvedProject, projectExt);
      resolvedPcb = resolvedPcb || join(projectDir, `${projectStem}.kicad_pcb`);
      resolvedSchematic = resolvedSchematic || join(projectDir, `${projectStem}.kicad_sch`);
    } else {
      projectDir = resolvedProject;
      projectStem = basename(resolvedProject);
    }
  }

  if (!resolvedPcb) {
    const info = await callKicadScript("get_project_info", {});
    const currentPath = info?.project?.path;
    if (info?.success && typeof currentPath === "string" && currentPath.endsWith(".kicad_pcb")) {
      resolvedPcb = currentPath;
      projectDir = dirname(currentPath);
      projectStem = basename(currentPath, ".kicad_pcb");
    }
  }

  if (!projectDir) {
    projectDir = "/private/tmp/kicad-mcp-viewer";
  }

  if (!resolvedPcb) {
    resolvedPcb = await findFirstFile(projectDir, ".kicad_pcb", projectStem);
  }
  if (!resolvedSchematic) {
    resolvedSchematic = await findFirstFile(projectDir, ".kicad_sch", projectStem);
  }

  if (resolvedPcb && !existsSync(resolvedPcb)) {
    resolvedPcb = undefined;
  }
  if (resolvedSchematic && !existsSync(resolvedSchematic)) {
    resolvedSchematic = undefined;
  }

  return { projectDir, pcbPath: resolvedPcb, schematicPath: resolvedSchematic };
}

export function registerViewerTools(server: McpServer, callKicadScript: CommandFunction): void {
  logger.info("Registering schematic/PCB viewer tools");

  server.tool(
    "capture_design_snapshot",
    "Render timestamped schematic and PCB snapshots for autonomous visual review. Saves files under snapshots/visual-feedback and can also return the images inline.",
    {
      projectPath: z
        .string()
        .optional()
        .describe("Project directory, .kicad_pro, .kicad_pcb, or .kicad_sch path. Falls back to current board."),
      schematicPath: z.string().optional().describe("Explicit .kicad_sch path to render"),
      pcbPath: z.string().optional().describe("Explicit .kicad_pcb path to render"),
      outputDir: z.string().optional().describe("Directory for snapshot files"),
      label: z.string().optional().describe("Snapshot label used in filenames"),
      includeSchematic: z.boolean().optional().describe("Render the schematic snapshot (default: true)"),
      includePcb: z.boolean().optional().describe("Render the PCB snapshot (default: true)"),
      includeImages: z.boolean().optional().describe("Return images inline as MCP image content (default: true)"),
      width: z.number().int().positive().optional().describe("Snapshot image width in pixels"),
      height: z.number().int().positive().optional().describe("Snapshot image height in pixels"),
      pcbLayers: z
        .array(z.string())
        .optional()
        .describe("Optional PCB layer names, e.g. [\"F.Cu\", \"F.SilkS\", \"Edge.Cuts\"]"),
    },
    async ({
      projectPath,
      schematicPath,
      pcbPath,
      outputDir,
      label,
      includeSchematic,
      includePcb,
      includeImages,
      width,
      height,
      pcbLayers,
    }) => {
      const paths = await resolveDesignPaths(callKicadScript, projectPath, pcbPath, schematicPath);
      const snapshotDir = resolve(outputDir || join(paths.projectDir, "snapshots", "visual-feedback"));
      await mkdir(snapshotDir, { recursive: true });

      const shouldRenderSchematic = includeSchematic !== false;
      const shouldRenderPcb = includePcb !== false;
      const shouldReturnImages = includeImages !== false;
      const snapLabel = safeLabel(label);
      const snapTime = timestamp();
      const files: Array<Record<string, unknown>> = [];
      const warnings: string[] = [];
      const content: Array<
        { type: "text"; text: string } | { type: "image"; data: string; mimeType: string }
      > = [];

      if (shouldRenderSchematic) {
        if (!paths.schematicPath) {
          warnings.push("No schematic path found; schematic snapshot skipped.");
        } else {
          const schematicResult = await callKicadScript("get_schematic_view", {
            schematicPath: paths.schematicPath,
            format: "png",
            width: width || 1800,
            height: height || 1300,
          });
          if (schematicResult?.success) {
            const format = schematicResult.format === "svg" ? "svg" : "png";
            const filePath = join(snapshotDir, `${snapTime}_${snapLabel}_schematic.${format}`);
            const data =
              format === "svg"
                ? Buffer.from(String(schematicResult.imageData || ""), "utf-8")
                : Buffer.from(String(schematicResult.imageData || ""), "base64");
            await writeFile(filePath, data);
            files.push({ kind: "schematic", path: filePath, format, source: paths.schematicPath });
            if (shouldReturnImages && format === "png") {
              content.push({
                type: "image",
                data: schematicResult.imageData,
                mimeType: "image/png",
              });
            }
          } else {
            warnings.push(`Schematic snapshot failed: ${schematicResult?.message || "unknown error"}`);
          }
        }
      }

      if (shouldRenderPcb) {
        if (!paths.pcbPath) {
          warnings.push("No PCB path found; PCB snapshot skipped.");
        } else {
          const pcbResult = await callKicadScript("get_board_2d_view", {
            pcbPath: paths.pcbPath,
            layers: pcbLayers,
            width: width || 1800,
            height: height || 1300,
            format: "png",
            responseMode: "inline",
          });
          if (pcbResult?.success) {
            const format = pcbResult.format === "svg" ? "svg" : "png";
            const filePath = join(snapshotDir, `${snapTime}_${snapLabel}_pcb.${format}`);
            await writeFile(filePath, Buffer.from(String(pcbResult.imageData || ""), "base64"));
            files.push({ kind: "pcb", path: filePath, format, source: paths.pcbPath, layers: pcbLayers });
            if (shouldReturnImages && format === "png") {
              content.push({
                type: "image",
                data: pcbResult.imageData,
                mimeType: "image/png",
              });
            }
          } else {
            warnings.push(`PCB snapshot failed: ${pcbResult?.message || "unknown error"}`);
          }
        }
      }

      const summary = {
        success: files.length > 0,
        message:
          files.length > 0
            ? `Captured ${files.length} visual snapshot${files.length === 1 ? "" : "s"}`
            : "No visual snapshots were captured",
        snapshotDir,
        projectDir: paths.projectDir,
        schematicPath: paths.schematicPath,
        pcbPath: paths.pcbPath,
        files,
        warnings,
      };

      content.unshift({ type: "text", text: JSON.stringify(summary, null, 2) });
      return { content, isError: files.length === 0 };
    },
  );
}

