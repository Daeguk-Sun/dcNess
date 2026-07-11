# Candidate

`CloudArchivePort` interface has no production implementation or caller in the current tree.

The current Epic architecture marks it `planned`, owner `archive`, first consumer `Epic 12 Story 1`. ADR-014 fixes the local/cloud seam now so encrypted archive policy does not leak into the domain. The impl task explicitly says to preserve the interface without a fake implementation until Epic 12.
