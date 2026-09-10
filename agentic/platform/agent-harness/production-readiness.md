# Production Readiness Checklist

The reference runtime provides enforceable local behavior but production deployment still requires organization-specific infrastructure.

- [ ] Shared durable database for workflow/checkpoint state
- [ ] Distributed worker queue and dead-letter queue
- [ ] Real Git provider adapter
- [ ] Real Jira/work-management adapter
- [ ] CI/CD adapter
- [ ] Central secret manager
- [ ] SSO/RBAC for approvals and tool calls
- [ ] Sandbox isolation and network policy
- [ ] DLP and secret scanning
- [ ] Prompt-injection controls at retrieval boundaries
- [ ] Central tracing/metrics backend
- [ ] Alerting and kill switches
- [ ] Concurrency/locking strategy
- [ ] Artifact retention and immutable audit policy
- [ ] Automated evals in CI
- [ ] Disaster recovery / backup policy
