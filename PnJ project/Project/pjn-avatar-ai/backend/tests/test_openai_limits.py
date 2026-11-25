import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from openai import RateLimitError
from app.travel import request_output


@pytest.mark.parametrize("code,kind,expected,calls", [
    ("credit_balance_exhausted","insufficient_quota","AI_CREDITS",1),
    ("insufficient_quota","insufficient_quota","AI_QUOTA",1),
    ("billing_hard_limit_reached","insufficient_quota","AI_SPEND",1),
    ("rate_limit_exceeded","tokens","AI_TOKENS",2),
    ("rate_limit_exceeded","requests","AI_REQUESTS",2),
    (None,None,"AI_LIMIT",1),
])
def test_attempts_and_public_error(code,kind,expected,calls):
    response = httpx.Response(429, headers={"retry-after":"0"}, request=httpx.Request("POST","https://example.invalid"))
    error = RateLimitError("limit", response=response, body={"code":code,"type":kind})
    with patch("app.travel.get_client") as client:
        parse = AsyncMock(side_effect=error)
        client.return_value.beta.chat.completions.parse = parse
        with pytest.raises(HTTPException) as exc:
            asyncio.run(request_output())
    assert (exc.value.status_code,exc.value.detail,parse.await_count) == (429,expected,calls)
