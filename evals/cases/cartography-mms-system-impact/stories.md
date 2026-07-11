# Epic 02 — MMS send and receive

- WAP push를 받아 multipart MMS를 저장한다.
- 저장된 attachment와 text part를 다시 읽는다.
- carrier transport로 MMS를 전송한다.
- 기존 MessageStore를 MMS canonical storage로 확장하고 SMS 조회와 함께 노출한다.
