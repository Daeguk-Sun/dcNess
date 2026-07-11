# Current code evidence

- `SmsReceiver`가 text-only payload를 `MessageStore`에 저장한다.
- MMS WAP push receiver, multipart parser, carrier send transport는 없다.
- `MessageStore` schema는 text body만 허용한다.
