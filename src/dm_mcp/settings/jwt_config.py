from pydantic import BaseModel, SecretStr


class JwtConfig(BaseModel):

    secret: SecretStr = SecretStr(
        "Z@>h}o^{YCMv?)Eip$_XX3bJ{q1eD-)DXzetG=KM0?yh>3$!:^NJk8Pu&!C)`u>"
    )

    # Token 过期时间（秒），默认1小时
    token_expire_seconds: int = 3600
