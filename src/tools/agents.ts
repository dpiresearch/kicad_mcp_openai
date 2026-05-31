/**
 * Parallel agent orchestration tools.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { spawn } from "child_process";
import { z } from "zod";
import { logger } from "../logger.js";

type AgentToolOptions = {
  agentScriptPath: string;
};

const AgentSchema = z.object({
  name: z.string().describe("Stable agent name, e.g. schematic_architect"),
  role: z.string().describe("Short engineering role for this agent"),
  instructions: z.string().optional().describe("Additional agent-specific instructions"),
});

function getAgentPythonExecutable(): string {
  return process.env.KICAD_AGENT_PYTHON || process.env.KICAD_PYTHON || "python3";
}

function callAgentOrchestrator(
  agentScriptPath: string,
  payload: Record<string, unknown>,
  timeoutMs: number,
): Promise<any> {
  return new Promise((resolve, reject) => {
    const pythonExe = getAgentPythonExecutable();
    const child = spawn(pythonExe, [agentScriptPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env },
    });

    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error(`Parallel agent orchestration timed out after ${timeoutMs / 1000}s`));
    }, timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (stderr.trim()) {
        logger.warn(`Parallel agent stderr: ${stderr.trim().slice(0, 1000)}`);
      }
      if (code !== 0) {
        reject(new Error(`Parallel agent process exited with ${code}: ${stderr || stdout}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (error) {
        reject(new Error(`Failed to parse parallel agent response: ${error}; output=${stdout}`));
      }
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

export function registerAgentTools(server: McpServer, options: AgentToolOptions): void {
  logger.info("Registering Modal/OpenAI parallel agent tools");

  server.tool(
    "get_parallel_agent_status",
    "Report whether Modal, the OpenAI Agents SDK, and OpenAI credentials are available for parallel KiCAD design agents.",
    {},
    async () => {
      const result = await callAgentOrchestrator(
        options.agentScriptPath,
        { command: "dependency_status", params: {} },
        30_000,
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    },
  );

  server.tool(
    "run_parallel_agents",
    "Fan out independent KiCAD design planning/review agents locally or on Modal, then return an aggregated action plan. Use this before applying complex schematic or PCB changes.",
    {
      task: z.string().describe("The KiCAD design task the parallel agents should analyze"),
      context: z.string().optional().describe("Relevant project details, file paths, constraints, or prior findings"),
      backend: z
        .enum(["auto", "local", "modal"])
        .default("auto")
        .describe("Execution backend. auto uses Modal when installed, otherwise local threads."),
      openai: z
        .enum(["auto", "off", "required"])
        .default("auto")
        .describe("Whether each agent should call the OpenAI Agents SDK when configured."),
      model: z.string().optional().describe("OpenAI model name for agent calls"),
      timeout_s: z.number().int().positive().max(1800).default(300).describe("Agent timeout in seconds"),
      max_workers: z
        .number()
        .int()
        .positive()
        .max(12)
        .default(4)
        .describe("Local parallel worker count"),
      agents: z
        .array(AgentSchema)
        .optional()
        .describe("Optional custom agent set. Defaults to schematic, layout, and DFM reviewers."),
    },
    async (args) => {
      const timeoutS = args.timeout_s ?? 300;
      const result = await callAgentOrchestrator(
        options.agentScriptPath,
        { command: "run_parallel_agents", params: args },
        (timeoutS + 15) * 1000,
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    },
  );
}

