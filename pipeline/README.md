# Monitor Casa Saturno — pipeline

Acompanhamento diário de postagens dos artistas da Casa Saturno no YouTube,
Instagram e TikTok. Alimenta o painel em https://casa-saturno.github.io/monitor/

## Arquivos

| | |
|---|---|
| `saturno.py` | Núcleo: upsert, contadores, leituras, export CSV. **As regras de integridade vivem aqui**, não em prompt. |
| `regen.py` | Gera `index.html` a partir da base + `painel_template.html`. |
| `painel_template.html` | Template do painel (placeholder `__DATA__`). |
| `base/*.csv` | Espelho versionado da base (diff legível, histórico auditável). |

## Regras de integridade (por que existem)

1. **A fonte decide o que pode ser gravado.** Todo `Post` carrega `fonte`.
   `ig_fallback` (web_profile_info) reporta uma métrica de views diferente da do
   feed — caso real observado: um post de 179k apareceu como 70k. O módulo
   **recusa** gravar views dessa fonte. O chamador não tem como errar.
2. **A origem do contador é explícita.** Cada snapshot de audiência grava
   `Origem`:
   - `medido` — leitura real naquela rodada.
   - `carry` — já foi medido antes, repetido por falha de coleta. Entre 24 e
     28/08/2026 *todos* os contadores foram carry por um bug — daí a regra.
   - `seed` — **nunca foi medido**. Valor semeado na criação da base. É o caso
     de todos os inscritos de YouTube (o RSS não expõe inscritos) e de 3 perfis
     de Instagram semeados com números redondos (Kysha, Kysha e Mine, Casa
     Saturno). Sem essa distinção, "estável" e "nunca medido" viram a mesma
     coisa para quem lê o painel.
3. **Leituras só de fonte consistente.** Trajetória (24/48/72h) nunca recebe
   número de fonte não-confiável.
4. **Ordem de coleta.** `PERFIS_PRIORIDADE` lê primeiro os perfis de maior
   volume: o rate-limit do Instagram castiga o fim da fila, e a Casa Saturno
   (que mais publica) era a última.

## Contrato da rodada

1. Carrega a base (fonte de verdade = este repositório).
2. Coleta: YouTube por RSS; Instagram por `/api/v1/feed/user/<uid>` com sessão
   logada, caindo para `web_profile_info` quando houver 401; TikTok best-effort.
3. `aplicar_posts` → `aplicar_contadores` → `aplicar_leituras` → `salvar`.
4. Regenera o painel e publica.

Janela de leituras: 7 dias. Fuso: America/Sao_Paulo (UTC-3).
