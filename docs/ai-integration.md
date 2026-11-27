# AI 분석 API 연결

로그인 세션이 필요한 GET `/api/analytics/recommendations/?space_id=1&date=2030-01-02`.
`date` 생략 시 한국 날짜 오늘. `space_id`는 `/api/spaces/`에서 받은 활성 공간 ID입니다.
기존 daily/summary API는 유지됩니다. summary의 예시 문구는 실제 분석 결과가 아닙니다.

응답은 데이터 팀의 schema_version 1.0 계약입니다.
`recommendations`는 하루 24개 시간대이며 `estimated_count`, `congestion_ratio`,
`congestion_level`, `confidence`, `recommended`, `reasons`, `history`를 포함합니다.
이메일, 닉네임, 참여자 ID, 세션 값은 결과에 포함하지 않습니다.

실제 현재 참여자를 중복 제거하며 모집 정원을 실제 인원으로 사용하지 않습니다.
취소된 일정은 제외하고 선택 날짜와 겹치는 일정만 DB에서 조회합니다.
데이터베이스 오류를 빈 결과로 바꾸지 않습니다. 캐시하지 않으며 매 요청 재계산합니다.

현재 연결 범위는 공간 하나입니다. 그 공간 정원만 사용하며 동방 전체 입퇴실과 채팅은
범위가 다르므로 적용하지 않습니다. 과거 기록의 완전 보존 기간이 확인되지 않아
history_start는 미설정입니다. 따라서 현재는 과거 통계가 없고 recommended는 false입니다.
이것은 연결 오류가 아닙니다. 표본 없이 확정 추천을 만들어내지 않는 데이터 팀 정책입니다.
예약이 없을 때 estimated_count=null은 '정보 부족'이며 0명으로 표시하면 안 됩니다.
실제 체류 인원의 예측 모델이 아닌 예약 신청 기반 추정입니다.

프론트는 날짜/공간 선택 시 조회하고 schedule.changed 및 재연결 후 재조회합니다.
운영 시간을 반영하지 않으므로 24개 구간 모두 방문 가능하다는 의미는 아닙니다.
과거 추천 활성화와 동방 전체 정원/공간 대응은 팀 확인 후 별도 확장합니다.

오류: 비로그인 401 authentication_required, 메서드 405,
잘못된 날짜 400 invalid_date, 공간 ID 400 invalid_space_id,
없거나 비활성인 공간 404 space_not_found.

추가 환경 변수, AI 키, DB 마이그레이션, 별도 AI 서버는 필요 없습니다.
main 병합 후 기존 Render 자동 배포를 사용합니다.
