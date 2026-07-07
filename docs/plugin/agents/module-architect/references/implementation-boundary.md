# 구현 경계 참고

impl 문서는 planner 문서다. engineer에게 무엇을 만족해야 하는지 알려야 하지만, 내부 구현을 대신 써서는 안 된다.

## 써야 하는 것

- public function, class, protocol의 signature
- caller가 알아야 하는 invariant
- 입력, 출력, 실패 방식
- 수정 허용 경계와 수정 금지 경계
- 검증 가능한 수용 기준

## 피해야 하는 것

- private helper 이름
- 테스트 함수명 강제
- loop body, list comprehension, try/catch 흐름 같은 내부 구현 의사코드
- 특정 라이브러리 호출 순서가 contract가 아닌데도 박아 넣는 것
- 기존 코드와 변경 후 코드를 긴 block으로 비교하는 것

## 예외

파서, 상태 머신, 정렬, 매칭처럼 알고리즘 자체가 contract인 경우에는 public behavior 흐름을 짧게 설명할 수 있다. 그래도 private 구조는 engineer 재량으로 남긴다.
