import fs from "node:fs/promises";
import path from "node:path";

const ROOT = process.cwd();
const action = process.env.METHOD_ACTION || "apply";
const approval = process.env.METHOD_APPROVAL || "";
const versionArg = process.env.METHOD_VERSION || "";
const proposalId = process.env.PROPOSAL_ID || "";

if (approval !== "AUTORIZO-ECG") throw new Error("Autorização explícita ausente. Informe METHOD_APPROVAL=AUTORIZO-ECG.");
const methodPath = path.join(ROOT, "data/metodo-aprovado.json");
const historyPath = path.join(ROOT, "data/historico-versoes.json");
const backupDir = path.join(ROOT, "backups/metodos");
const now = new Date().toISOString().replace(/[:.]/g, "-");
const method = JSON.parse(await fs.readFile(methodPath, "utf8"));
let history = [];
try { history = JSON.parse(await fs.readFile(historyPath, "utf8")); } catch {}
await fs.mkdir(backupDir, { recursive: true });

function validateConfig(config) {
  for (const game of ["lotofacil", "megasena"]) {
    const item = config.modalidades?.[game];
    if (!item || !Array.isArray(item.pesos_frequencia) || item.pesos_frequencia.length !== 6) throw new Error("Configuração inválida: " + game);
    const weights = item.pesos_frequencia.map(Number);
    if (weights.some(x => !Number.isFinite(x) || x < 0 || x > 1) || Math.abs(weights.reduce((a,b)=>a+b,0)-1) > 1e-8) throw new Error("Pesos devem somar 1 em " + game);
    if (!Number.isFinite(Number(item.peso_estrutural)) || item.peso_estrutural < 0 || item.peso_estrutural > 1) throw new Error("Peso estrutural inválido em " + game);
  }
}
validateConfig(method);

if (action === "restore") {
  if (!/^v[0-9]+\.[0-9]+\.[0-9]+$/.test(versionArg)) throw new Error("Informe METHOD_VERSION no formato vX.Y.Z.");
  const source = path.join(ROOT, "backups/metodos", versionArg + ".json");
  const restored = JSON.parse(await fs.readFile(source, "utf8"));
  validateConfig(restored);
  await fs.copyFile(methodPath, path.join(backupDir, method.version_id + "-before-restore-" + now + ".json"));
  const previous = method.version_id;
  restored.parent_version = previous;
  restored.version_id = versionArg;
  restored.updated_at = new Date().toISOString();
  restored.status = "restaurado_com_autorizacao";
  await fs.writeFile(methodPath, JSON.stringify(restored, null, 2) + "\n");
  history.push({event:"restore",from:previous,to:restored.version_id,source_version:versionArg,at:restored.updated_at,authorized:true});
  await fs.writeFile(historyPath, JSON.stringify(history, null, 2) + "\n");
  console.log("Backup restaurado: " + versionArg + " -> " + restored.version_id);
  process.exit(0);
}
if (action !== "apply") throw new Error("METHOD_ACTION deve ser apply ou restore.");
if (!/^[a-z0-9][a-z0-9-]{2,70}$/.test(proposalId)) throw new Error("PROPOSAL_ID inválido.");
const proposalPath = path.join(ROOT, "proposals", proposalId + ".json");
const proposal = JSON.parse(await fs.readFile(proposalPath, "utf8"));
if (proposal.id !== proposalId) throw new Error("ID da proposta não confere.");
if (proposal.status !== "aprovavel" || proposal.evidencia?.replicacao_confirmada !== true || !Number.isFinite(Number(proposal.evidencia?.ic95_inferior_vs_ecg_original)) || Number(proposal.evidencia.ic95_inferior_vs_ecg_original) <= 0) {
  throw new Error("Proposta bloqueada: exige replicação confirmada e IC95% pareado inteiramente acima de zero contra ECG original.");
}
if (!proposal.modalidades) throw new Error("Proposta sem parâmetros completos.");
const next = {
  schema_version: 1,
  version_id: proposal.version_sugerida,
  parent_version: method.version_id,
  updated_at: new Date().toISOString(),
  status: "aplicado_com_autorizacao",
  proposta_id: proposalId,
  evidencia: proposal.evidencia,
  modalidades: proposal.modalidades,
  nota: proposal.justificativa || "Alteração aprovada pelo responsável."
};
if (!/^v[0-9]+\.[0-9]+\.[0-9]+$/.test(next.version_id || "")) throw new Error("Versão sugerida inválida.");
validateConfig(next);
const backupPath = path.join(backupDir, method.version_id + ".json");
try { await fs.access(backupPath); } catch { await fs.copyFile(methodPath, backupPath); }
await fs.writeFile(methodPath, JSON.stringify(next, null, 2) + "\n");
history.push({event:"apply",proposal_id:proposalId,from:method.version_id,to:next.version_id,at:next.updated_at,authorized:true,evidence:proposal.evidencia});
await fs.writeFile(historyPath, JSON.stringify(history, null, 2) + "\n");
console.log("Método atualizado com autorização: " + method.version_id + " -> " + next.version_id);
