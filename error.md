# AI Token Generation - List Index Out Of Range Error

## 🚨 에러 개요 (Problem)
`protostar-fastapi`의 AI 스트리밍 토큰 생성 시 간헐적으로 `IndexError: list index out of range`가 발생하여 응답 생성이 중간에 중단되는 현상.

## 🕵️ 원인 분석 (Root Cause)
OpenRouter와 같은 AI API 연동 과정(`app/core/ai.py`)에서 스트리밍 청크(`chunk`) 혹은 최종 응답(`response`)을 받아올 때 데이터가 비어 있거나 빈 배열 형태로 전달되는 경우가 있습니다. 이 구조에서 `choices` 배열의 길이를 검증하지 않고 하드코딩된 `[0]`번 인덱스에 접근하려다 파이썬에서 에러를 던진 것입니다.

해당 문제가 발생하는 2곳의 위험 코드는 아래와 같습니다:

1. **`generate_response_stream` (스트리밍 중)**
   ```python
   async for chunk in stream:
       content = chunk.choices[0].delta.content # ❌ 빈 배열일 경우 여기서 에러 발생
       if content:
           yield content
   ```

2. **`generate_summary` (단일 응답 처리 중)**
   ```python
   # ❌ 응답 choices가 비어 있을 경우 에러 발생 위험
   summary_text = response.choices[0].message.content.strip()
   ```


## 🛠️ 해결 방안 (Solution)
배열 요소(`choices`)에 접근하기 전, 해당 속성이 존재하고 요소의 길이가 0보다 큰지 먼저 검증하는 방어 코드를 추가해야 합니다.

**1. `generate_response_stream` 수정안:**
```python
async for chunk in stream:
    # ✅ choices 가 존재하고 1개 이상의 요소를 가졌을 때만 접근
    if getattr(chunk, "choices", None) and len(chunk.choices) > 0:
        content = chunk.choices[0].delta.content
        if content:
            yield content
```

**2. `generate_summary` 수정안:**
```python
# ✅ choices 가 존재하는지 먼저 검증, 없으면 원본 텍스트를 일부 반환하여 에러 방지
if getattr(response, "choices", None) and len(response.choices) > 0:
    summary_text = response.choices[0].message.content.strip()
else:
    summary_text = original_text[:500]
    
usage_info = getattr(response, "usage", None)
```
