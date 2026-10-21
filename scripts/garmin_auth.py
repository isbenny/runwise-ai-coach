#!/usr/bin/env python3
"""TTY/privacy wrapper only; authentication is delegated unchanged upstream."""
import argparse
from contextlib import redirect_stdout,redirect_stderr
import getpass
import io
import os
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--state-dir',type=Path,required=True);a=p.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty():raise RuntimeError('LOCAL_TTY_REQUIRED_NO_CREDENTIALS_IN_CHAT')
    if any(os.getenv(k) for k in ['GARMIN_EMAIL','GARMIN_PASSWORD','GARMIN_EMAIL_FILE','GARMIN_PASSWORD_FILE']):raise RuntimeError('CREDENTIAL_ENV_NOT_ALLOWED')
    folder=a.state_dir.absolute()
    if folder.is_symlink() or (folder.exists() and folder.stat().st_mode&0o077):raise RuntimeError('PRIVATE_NEW_OR_OWNER_ONLY_STATE_REQUIRED')
    folder.mkdir(parents=True,mode=0o700,exist_ok=True);os.umask(0o077)
    cache=folder/'tokens';cache.mkdir(mode=0o700,exist_ok=True)
    if cache.is_symlink() or cache.stat().st_mode&0o077:raise RuntimeError('PRIVATE_CACHE_REQUIRED')
    os.environ['GARMIN_IS_CN']='true';os.environ['GARMINTOKENS']=str(cache)
    os.environ['GARMINTOKENS_BASE64']=str(folder/'tokens.base64')
    from garmin_mcp import auth_cli
    def credentials():
        return getpass.getpass('佳明中国区账号（本机隐藏输入）：',stream=sys.__stderr__).strip(),getpass.getpass('密码（本机隐藏输入）：',stream=sys.__stderr__)
    auth_cli.get_credentials=credentials
    auth_cli.get_mfa=lambda:getpass.getpass('验证码（本机隐藏输入）：',stream=sys.__stderr__)
    # Upstream prints the email/name and may echo exception details. Never log it.
    with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
        ok=auth_cli.authenticate(str(cache),str(folder/'tokens.base64'),is_cn=True)
    print('认证成功，缓存仅存本人私有目录。' if ok else '认证未通过，已停止。请本人核对，不发送凭据或完整日志。')
    return 0 if ok else 2


if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,ImportError) as exc:
        print(str(exc) if isinstance(exc,RuntimeError) else 'INSTALL_PINNED_GARMIN_MCP_FIRST',file=sys.stderr);sys.exit(2)
    except KeyboardInterrupt:sys.exit(130)
    except Exception:print('LOCAL_AUTH_FAILED_NO_SECRET_LOGGED',file=sys.stderr);sys.exit(2)
