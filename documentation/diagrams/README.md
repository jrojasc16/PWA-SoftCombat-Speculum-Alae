# Diagramas UML — PWA Ranking Elo Speculum-Alae (MVP)

Fuentes versionables de los diagramas que reemplazan a los del documento original. Cada diagrama existe en dos sintaxis:

- **`.puml`** — PlantUML (referencia principal; soporta nativamente casos de uso y WBS).
- **`.mmd`** — Mermaid (alternativa renderizable en GitHub/Markdown; casos de uso, paquetes y despliegue son aproximaciones con `flowchart`, sin soporte nativo).

| Diagrama | Archivos | Requisitos cubiertos |
|---|---|---|
| Casos de uso | `casos_de_uso.{puml,mmd}` | RF1–RF14 (nuevo alcance) |
| Clases | `clases.{puml,mmd}` | RF6, RF7, RF8, RF9, RF10 |
| Paquetes | `paquetes.{puml,mmd}` | Arquitectura (propuesta §5) |
| Secuencia 01 — Reporte online | `secuencia_01_reporte_online.{puml,mmd}` | RF6 |
| Secuencia 02 — Offline + sync | `secuencia_02_offline_sync.{puml,mmd}` | RF5, RF14 |
| Secuencia 03 — Confirmación y prioridad árbitro | `secuencia_03_confirmacion_arbitro.{puml,mmd}` | RF7, RF8, RF9, RNF008 |
| Secuencia 04 — Ranking público vía WordPress | `secuencia_04_wordpress_ranking.{puml,mmd}` | RF11, RF12, RNF002 |
| Despliegue | `despliegue.{puml,mmd}` | RNF001, RNF004, RNF009 |
| EDT (WBS) | `edt.{puml,mmd}` | Alcance del proyecto |

## Cómo exportar a PNG (para insertar en el .docx)

```bash
# PlantUML (requiere Java): https://plantuml.com/download
java -jar plantuml.jar -tpng diagrams/*.puml

# Mermaid CLI:
npx -y @mermaid-js/mermaid-cli -i casos_de_uso.mmd -o casos_de_uso.png
```

También se pueden pegar en <https://www.plantuml.com/plantuml> o <https://mermaid.live> sin instalar nada.

> Al editar un diagrama, edita **ambas sintaxis** para mantenerlas sincronizadas. La versión PlantUML es la fuente de verdad.
