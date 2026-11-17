import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const sourceRoot = process.cwd();
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "ecg-promotion-test-"));
const run = (env) => spawnSync(process.execPath, [path.join(temp, "scripts/apply-approved-method.mjs")], {
  cwd: temp, env: { ...process.env, ...env }, encoding: "utf8"
});
try {
  fs.mkdirSync(path.join(temp, "scripts"), { recursive: true });
  fs.mkdirSync(path.join(temp, "data"), { recursive: true });
  fs.mkdirSync(path.join(temp, "proposals"), { recursive: true });
  fs.mkdirSync(path.join(temp, "backups/metodos"), { recursive: true });
  fs.copyFileSync(path.join(sourceRoot, "scripts/apply-approved-method.mjs"), path.join(temp, "scripts/apply-approved-method.mjs"));
  const original = {
    schema_version: 1, version_id: "v1.0.0", parent_version: null,
    modalidades: {
      lotofacil: { pesos_frequencia: [0.35,0.2,0.15,0.1,0.1,0.1], peso_estrutural: 0.3 },
      megasena: { pesos_frequencia: [0.35,0.2,0.15,0.1,0.1,0.1], peso_estrutural: 0.3 }
    }
  };
  fs.writeFileSync(path.join(temp, "data/metodo-aprovado.json"), JSON.stringify(original, null, 2));
  fs.writeFileSync(path.join(temp, "data/historico-versoes.json"), "[]\n");
  const proposal = {
    id: "teste-ciclo-ecg",
    version_sugerida: "v1.0.1",
    status: "aprovavel",
    evidencia: {
      replicacao_confirmada: true,
      ic95_inferior_vs_ecg_original: 0.001,
      observacao: "FIXTURE SINTÉTICO EXCLUSIVO PARA TESTE DE INTEGRAÇÃO; NÃO É EVIDÊNCIA ESTATÍSTICA REAL."
    },
    modalidades: {
      lotofacil: { pesos_frequencia: [0.3,0.2,0.15,0.15,0.1,0.1], peso_estrutural: 0.31 },
      megasena: { pesos_frequencia: [0.3,0.2,0.15,0.15,0.1,0.1], peso_estrutural: 0.31 }
    },
    justificativa: "Fixture isolado de integração, sem efeito no método de produção."
  };
  fs.writeFileSync(path.join(temp, "proposals/teste-ciclo-ecg.json"), JSON.stringify(proposal, null, 2));

  const noApproval = run({ METHOD_ACTION: "apply", METHOD_APPROVAL: "NAO", PROPOSAL_ID: proposal.id });
  assert.notEqual(noApproval.status, 0, "A aplicação sem autorização deve falhar.");
  assert.equal(JSON.parse(fs.readFileSync(path.join(temp, "data/metodo-aprovado.json"))).version_id, "v1.0.0");

  const applied = run({ METHOD_ACTION: "apply", METHOD_APPROVAL: "AUTORIZO-ECG", PROPOSAL_ID: proposal.id });
  assert.equal(applied.status, 0, applied.stderr || applied.stdout);
  const current = JSON.parse(fs.readFileSync(path.join(temp, "data/metodo-aprovado.json")));
  assert.equal(current.version_id, "v1.0.1");
  assert.equal(current.parent_version, "v1.0.0");
  assert.ok(fs.existsSync(path.join(temp, "backups/metodos/v1.0.0.json")));
  let history = JSON.parse(fs.readFileSync(path.join(temp, "data/historico-versoes.json")));
  assert.equal(history.length, 1);
  assert.equal(history[0].event, "apply");
  assert.equal(history[0].authorized, true);

  const restored = run({ METHOD_ACTION: "restore", METHOD_APPROVAL: "AUTORIZO-ECG", METHOD_VERSION: "v1.0.0" });
  assert.equal(restored.status, 0, restored.stderr || restored.stdout);
  const finalMethod = JSON.parse(fs.readFileSync(path.join(temp, "data/metodo-aprovado.json")));
  assert.equal(finalMethod.version_id, "v1.0.0");
  assert.deepEqual(finalMethod.modalidades, original.modalidades);
  history = JSON.parse(fs.readFileSync(path.join(temp, "data/historico-versoes.json")));
  assert.equal(history.length, 2);
  assert.equal(history[1].event, "restore");
  assert.equal(history[1].source_version, "v1.0.0");
  assert.equal(history[1].authorized, true);
  console.log("OK: bloqueio sem autorização; aplicação v1.0.1; backup v1.0.0; restauração v1.0.0; trilha de auditoria preservada.");
  console.log("NOTA: proposta e evidência são fixtures sintéticos de teste, nunca dados reais nem melhoria aprovada.");
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
