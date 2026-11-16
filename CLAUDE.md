# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

> 위 4원칙의 출처: https://github.com/forrestchang/andrej-karpathy-skills (MIT)

## 추가 규칙

### 비판적 검토
- 구현 전에 요구사항 자체를 검토한다: 목적에 맞는가, 더 싸고 단순한 방법이 있는가, 전제가 사실인가.
- 치명적 결함(데이터 손실, 되돌릴 수 없는 변경, 유료 크레딧·API 비용, 보안·계정 위험, 요구사항끼리 모순)은 작업 전에 보고하고 멈춘다.
- 그 외 문제는 진행하되 결과 보고 맨 위에 심각도 순 최대 3개를 적는다. 없으면 "치명적 결함 없음"이라고 쓴다.

### 완료 전 검증
- "완료"라고 보고하기 전에 결과물을 실제로 열어서 확인한다. 웹페이지는 브라우저로 열어 화면과 콘솔 에러를 보고, 버튼·링크·입력란을 전부 눌러본다.
- 삭제·결제·발송·외부 게시처럼 되돌릴 수 없는 버튼은 누르지 않고 목록으로 보고한다.
- 요청받은 과정 전체를 처음부터 끝까지 한 번 돌려 에러가 없는지 확인한다.
- 확인하지 못한 항목은 "미검증"이라고 쓰고 이유를 적는다.

### 예약(무인) 실행
- 사람이 없는 예약 실행에서는 질문으로 멈추지 않는다. 가장 합리적인 해석으로 진행하고, 보고 맨 위에 어떤 가정을 했는지 적는다.
