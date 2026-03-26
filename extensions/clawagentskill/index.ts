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

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString())); }
      catch { resolve({}); }
    });
    req.on("error", reject);
  });
}

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

function runCliJson(pythonBin, repoRoot, args, timeoutMs) {
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
          reject(new Error(stderr?.trim() || error.message));
          return;
        }
        resolve({
          success: true,
          output: stdout?.trim() ?? "",
          stderr: stderr?.trim() ?? "",
        });
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

  // --- HTTP webhook routes ---

  api.registerHttpRoute({
    path: "/clawagentskill/find",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["-m", "clawagentskill", "find"];
      if (body.query) args.push(String(body.query));
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/adopt",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["-m", "clawagentskill", "adopt"];
      if (body.source) args.push(String(body.source));
      if (body.name) args.push(String(body.name));
      if (body.execution_style) args.push("--execution-style", String(body.execution_style));
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/port",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["-m", "clawagentskill", "port"];
      if (body.source) args.push(String(body.source));
      if (body.name) args.push(String(body.name));
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/scan",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["-m", "clawagentskill", "scan"];
      if (body.file_path) args.push(String(body.file_path));
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/status",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const args = ["-m", "clawagentskill", "status"];
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/state-init",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const args = ["-m", "clawagentskill", "state-init"];
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/validate-prereqs",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const args = ["-m", "clawagentskill", "validate-prereqs"];
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawagentskill/get-field",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["-m", "clawagentskill", "get-field"];
      if (body.field) args.push(String(body.field));
      if (body.file_path) args.push(String(body.file_path));
      try {
        const result = await runCliJson(pythonBin, repoRoot, args, timeoutMs);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  console.log(`[clawagentskill] tool + 8 HTTP routes registered`);
}

export function activate(api) {
  register(api);
}

export default { register, activate };
