# Code validation observation

구현 diff와 impact는 서로 일치하고 system boundary, owner, storage policy, global decision은 바뀌지 않았다. 그러나 현재 Root에는 attachment export가 planned, CLI가 stub으로 남아 있고 새 CLI→entrypoint→ExportService edge가 없다. affected Root route/state/as-built edge refresh와 그 뒤 재검증이 필요하다.
