# Frozen candidate — conversation recipient correction

## Product contract

- 스레드 목록과 상세 상단은 현재 canonical 상대 번호를 일관되게 보여야 한다.
- 답장과 재전송은 자기 번호가 아니라 현재 canonical 상대에게만 발송돼야 한다.
- 알림 deep link는 단일 스레드 화면을 여는 `simple=true` 계약을 보존해야 한다.

## Final diff summary

1. `refreshThread(threadId)`는 provider의 canonical recipient를 읽어 상세 화면 상단 주소를 고친다.
2. 목록 `sync()`는 메시지 변경이 감지된 thread만 다시 저장한다. 메시지 변화가 없는 기존 thread row의 저장 주소는 비교하거나 self-heal하지 않는다.
3. 새 답장은 `threadId`로 canonical recipient를 조회한다.
4. 재전송은 canonical recipient 조회 전에 실행될 수 있고, 조회 결과가 없으면 선택한 개별 메시지의 address를 발송 주소로 사용한다. 발신 MMS의 개별 message address는 사용자 자기 번호일 수 있다.
5. 알람 notification deep link는 `nexus://messages/thread/{threadId}`를 만들지만 query parameter는 붙이지 않는다. 화면 router는 `simple=true`일 때만 단일 스레드 mode로 연다.

## Evidence

- focused unit tests는 상세 상단 canonical 주소와 새 답장 경로만 검증한다.
- lint/build/unit suite는 exit 0이다.
- 목록의 기존 row, 발신 MMS 재전송, notification tap route에 대한 assertion은 없다.
