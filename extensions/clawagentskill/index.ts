// @ts-nocheck
import { execFile } from "child_process";
import path from "path";

const TOOL_NAME = "clawagentskill";

const TOOL_SCHEMA = {
  name: TOOL_NAME,
  description:
    "Agent and skill discovery, security scanning, and adoption via the ClawAgentSkill CLI. Supports finding skills/agents by query, adopting from external sources, porting Claude Code agents, security scanning SKILL.md files, and Lobster-compatible state management.",
  parameters: {
    type: "object",
    required: ["action"],
    additionalProperties: false,
    properties: {
      action: {
        type: "string",
        enum: [
          "find",
          "adopt",
          "port",
          "scan",
          "status",
          "state-init",
          "validate-prereqs",
          "get-field",
        ],
        description:
          "CLI subcommand to execute. find: search for skills/agents by query. adopt: adopt a skill/agent from an external source. port: port a Claude Code agent to OpenClaw. scan: security scan a SKILL.md file. status: show recent adoption runs. state-init: create a Lobster-compatible run directory. validate-prereqs: check required binaries on PATH. get-field: read a field from meta.yaml.",
      },
      query: {
        type: "string",
        description: "Search query string (used with action=find).",
      },
      source: {
        type: "string",
        description:
          "Source identifier for adoption, e.g. a GitHub URL, ClawHub slug, or local path (used with action=adopt).",
      },
      skill_id: {
        type: "string",
        description:
          "Skill or agent identifier within the source (used with action=adopt).",
      },
      file_path: {
        type: "string",
        description:
          "Path to the file to scan or port (used with action=scan or action=port).",
      },
      run_dir: {
        type: "string",
        description:
          "Run directory path for Lobster-compatible state operations (used with action=state-init or action=get-field).",
      },
      field: {
        type: "string",
        description:
          "Field name to read from meta.yaml (used with action=get-field).",
      },
      execution_style: {
        type: "string",
        enum: ["accept_recommendations", "interactive"],
        description:
          "Adoption execution style. accept_recommendations: apply recommended defaults automatically. interactive: prompt for confirmation at each step (used with action=adopt).",
      },
    },
  },
};

function buildArgs(params) {
  const { action, query, source, skill_id, file_path, run_dir, field, execution_style } = params;
  const args = ["-m", "clawagentskill", action];

  switch (action) {
    case "find":
      if (query) args.push(query);
      break;

    case "adopt":
      if (source) args.push(source);
      if (skill_id) args.push(skill_id);
      if (execution_style) args.push("--execution-style", execution_style);
      break;

    case "port":
      if (file_path) args.push(file_path);
      break;

    case "scan":
      if (file_path) args.push(file_path);
      break;

    case "status":
      // no additional args
      break;

    case "state-init":
      if (run_dir) args.push(run_dir);
      break;

    case "validate-prereqs":
      // no additional args
      break;

    case "get-field":
      if (run_dir) args.push(run_dir);
      if (field) args.push(field);
      break;

    default:
      break;
  }

  return args;
}

function runCli(pythonBin, repoRoot, args, timeoutMs) {
  return new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, "clawagentskill", "src"),
    };

    execFile(
      pythonBin,
      args,
      { cwd: repoRoot, env, timeout: timeoutMs },
      (error, stdout, stderr) => {
        if (error) {
          const message = stderr?.trim() || error.message;
          reject(new Error(`clawagentskill CLI error: ${message}`));
          return;
        }
        resolve(stdout?.trim() ?? "");
      }
    );
  });
}

export function register(api) {
  const pluginConfig = api.config ?? {};
  const repoRoot =
    pluginConfig.repoRoot ??
    process.env.OPENCLAW_WORKSPACE ??
    process.cwd();
  const pythonBin =
    pluginConfig.pythonBin ??
    path.join(repoRoot, "clawpipe", ".venv", "bin", "python");
  const timeoutMs = pluginConfig.timeoutMs ?? 60000;

  api.registerTool(TOOL_SCHEMA, async (params) => {
    const args = buildArgs(params);

    try {
      const output = await runCli(pythonBin, repoRoot, args, timeoutMs);
      return { content: output || "(no output)" };
    } catch (err) {
      return { error: err.message };
    }
  });

  console.log(`[clawagentskill] tool registered`);
}

export function activate(api) {
  register(api);
}

export default { register, activate };
