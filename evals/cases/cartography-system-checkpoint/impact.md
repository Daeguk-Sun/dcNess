# Build impact

- runtime entrypoint: public REST removed, event stream added
- capability/state owner: IngestGateway → StreamIngress
- dependency edge: external client → REST removed; broker → StreamIngress added
- public surface: breaking change
- state before/after: REST route landed → removed, stream route planned → landed
- related epic/decision: epic-03 ingest, ADR-0004 public REST contract
