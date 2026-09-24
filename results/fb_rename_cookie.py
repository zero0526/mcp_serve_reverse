#!/usr/bin/env python3
"""Script tái hiện chuỗi API đổi tên tài khoản Facebook Accounts Center qua Cookie.

Được trích xuất và tổng hợp tự động từ Task ID: task_b528f651 qua bộ công cụ MCP api_lineage.
Bao gồm:
1. Trích xuất tự động account_id từ cookie (c_user)
2. Tự động crawl HTML Accounts Center để trích xuất CSRF Token (fb_dtsg, lsd, revision)
3. Tính toán chữ ký động jazoest = "2" + sum(ord(c) for c in fb_dtsg)
4. Validate tên mới qua GraphQL Query (useFXIMNameValidatorQuery - DocID: 26692801570319630)
5. Thực thi đổi tên qua GraphQL Mutation (useFXIMUpdateNameMutation - DocID: 9538143859625836)
6. Hỗ trợ xử lý thử thách bảo mật 2FA nếu tài khoản yêu cầu xác thực hai bước (useTwoFactorLoginValidateCodeMutation)
"""

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from typing import Any

import httpx

# Cấu hình mặc định thu thập từ task_b528f651
DEFAULT_COOKIE = (
    "sb=lluqauTrWKoHO_N-dS4RtBsC; ps_l=1; ps_n=1; datr=Ngiyapqs4bcZRvU1stox3erE; "
    "locale=en_US; c_user=61586402792082; "
    "xs=42%3AuuU33WkWko45lw%3A2%3A1790242273%3A-1%3A-1%3A%3AAcwqLgaN5q5BYDZBSxvPnlivP4xdPvjVrezc7Dzg_g; "
    "fr=1CmSpM1vtB41HOX2G.AWf0tczeMfKYTkzU7Sh-LAzVZnC9VKhLA1uz_GC6UIBgkqRQ_K4.BqtO3o..AAA.0.0.BqtO3r.AWeKbJXY2jptin9IyKgQzEFvfUs; "
    "wd=1129x945"
)

DOC_ID_VALIDATE_NAME = "26692801570319630"
DOC_ID_PREVIEW_NAME = "26302360049350115"
DOC_ID_UPDATE_NAME = "9538143859625836"
DOC_ID_2FA_ROOT_QUERY = "26677319665197312"
DOC_ID_2FA_SEND_CODE = "27297512486584094"
DOC_ID_2FA_VALIDATE = "26264014419868193"


def calculate_jazoest(fb_dtsg: str) -> str:
    """Tính toán tham số băm jazoest từ chuỗi fb_dtsg."""
    return "2" + str(sum(ord(c) for c in fb_dtsg))


def extract_account_id(cookie_string: str) -> str | None:
    """Trích xuất c_user (account_id) từ chuỗi cookie."""
    match = re.search(r"(?:^|;\s*)c_user=(\d+)", cookie_string)
    return match.group(1) if match else None


def build_common_headers(cookie_string: str, lsd: str, account_id: str, friendly_name: str) -> dict[str, str]:
    """Tạo headers chuẩn hóa cho request GraphQL Facebook Accounts Center."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": friendly_name,
        "X-FB-LSD": lsd,
        "X-ASBD-ID": "359341",
        "Origin": "https://accountscenter.facebook.com",
        "Referer": f"https://accountscenter.facebook.com/profiles/{account_id}/name/?entrypoint=fb_account_center",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Cookie": cookie_string,
    }


async def fetch_tokens_from_page(
    client: httpx.AsyncClient, cookie_string: str, account_id: str
) -> dict[str, str]:
    """Crawl trang Accounts Center để trích xuất fb_dtsg, lsd và server_revision."""
    url = f"https://accountscenter.facebook.com/profiles/{account_id}/name/?entrypoint=fb_account_center"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": cookie_string,
    }

    resp = await client.get(url, headers=headers, follow_redirects=True)
    html = resp.text

    # 1. Trích xuất fb_dtsg
    dtsg_match = re.search(r'"DTSGInitialData"[^\}]*?"token":"([^"]+)"', html)
    fb_dtsg = dtsg_match.group(1) if dtsg_match else None
    if not fb_dtsg:
        alt_dtsg = re.search(r'name="fb_dtsg"\s+value="([^"]+)"', html)
        fb_dtsg = alt_dtsg.group(1) if alt_dtsg else None

    # 2. Trích xuất lsd
    lsd_match = re.search(r'"LSD"[^\}]*?"token":"([^"]+)"', html)
    lsd = lsd_match.group(1) if lsd_match else None
    if not lsd:
        alt_lsd = re.search(r'name="lsd"\s+value="([^"]+)"', html)
        lsd = alt_lsd.group(1) if alt_lsd else None

    # 3. Trích xuất server_revision
    rev_match = re.search(r'"server_revision":(\d+)', html)
    rev = rev_match.group(1) if rev_match else "1048361770"

    if not fb_dtsg:
        raise ValueError("Không thể tìm thấy token fb_dtsg trong HTML response. Cookie có thể đã hết hạn.")

    return {
        "fb_dtsg": fb_dtsg,
        "lsd": lsd or "zCqJoMpmeaHmvrUSYVru8s",
        "revision": rev,
    }


async def validate_name(
    client: httpx.AsyncClient,
    cookie_string: str,
    tokens: dict[str, str],
    account_id: str,
    first_name: str,
    middle_name: str,
    last_name: str,
) -> dict[str, Any]:
    """Gọi useFXIMNameValidatorQuery để kiểm tra hợp lệ của họ tên mới."""
    endpoint = "https://accountscenter.facebook.com/api/graphql/"
    friendly_name = "useFXIMNameValidatorQuery"
    headers = build_common_headers(cookie_string, tokens["lsd"], account_id, friendly_name)

    variables = {
        "identity_ids": [account_id],
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "scale": 1,
        "platform": "FACEBOOK",
    }

    form_data = {
        "av": account_id,
        "__user": account_id,
        "__a": "1",
        "__comet_req": "5",
        "__rev": tokens["revision"],
        "fb_dtsg": tokens["fb_dtsg"],
        "jazoest": calculate_jazoest(tokens["fb_dtsg"]),
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_VALIDATE_NAME,
    }

    res = await client.post(endpoint, headers=headers, data=form_data)
    return res.json()


async def execute_rename(
    client: httpx.AsyncClient,
    cookie_string: str,
    tokens: dict[str, str],
    account_id: str,
    first_name: str,
    middle_name: str,
    last_name: str,
    full_name_format: str | None = None,
) -> dict[str, Any]:
    """Thực thi mutation đổi tên useFXIMUpdateNameMutation."""
    endpoint = "https://accountscenter.facebook.com/api/graphql/"
    friendly_name = "useFXIMUpdateNameMutation"
    headers = build_common_headers(cookie_string, tokens["lsd"], account_id, friendly_name)

    # Nếu không chỉ định định dạng hiển thị, tự ghép họ + tên
    full_name = full_name_format or (f"{last_name} {first_name}" if not middle_name else f"{last_name} {middle_name} {first_name}")

    mutation_id = str(uuid.uuid4())
    variables = {
        "client_mutation_id": mutation_id,
        "family_device_id": "device_id_fetch_datr",
        "identity_ids": [account_id],
        "full_name": full_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "interface": "FB_WEB",
    }

    form_data = {
        "av": account_id,
        "__user": account_id,
        "__a": "1",
        "__comet_req": "5",
        "__rev": tokens["revision"],
        "__spin_r": tokens["revision"],
        "__spin_b": "trunk",
        "__spin_t": str(int(time.time())),
        "__crn": "comet.fx.accounts_center.name.editor",
        "fb_dtsg": tokens["fb_dtsg"],
        "jazoest": calculate_jazoest(tokens["fb_dtsg"]),
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_UPDATE_NAME,
    }

    res = await client.post(endpoint, headers=headers, data=form_data)
    return res.json()


async def query_2fa_default_method(
    client: httpx.AsyncClient,
    cookie_string: str,
    tokens: dict[str, str],
    account_id: str,
    encrypted_context: str,
) -> dict[str, str]:
    """Truy vấn phương thức xác thực 2FA mặc định (Email, SMS...) và địa chỉ nhận mã đã mask."""
    endpoint = "https://accountscenter.facebook.com/api/graphql/"
    friendly_name = "TwoStepVerificationRootQuery"
    headers = build_common_headers(cookie_string, tokens["lsd"], account_id, friendly_name)

    variables = {
        "doesRequireTwoFacData": True,
        "encryptedContext": encrypted_context,
    }

    form_data = {
        "av": account_id,
        "__user": account_id,
        "__a": "1",
        "__comet_req": "5",
        "__rev": tokens["revision"],
        "fb_dtsg": tokens["fb_dtsg"],
        "jazoest": calculate_jazoest(tokens["fb_dtsg"]),
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_2FA_ROOT_QUERY,
    }

    res = await client.post(endpoint, headers=headers, data=form_data)
    data = res.json().get("data") or {}
    default_method = data.get("xfb_two_factor_login_default_method", {}).get("method") or {}
    return {
        "method": default_method.get("method") or "EMAIL",
        "representation": default_method.get("method_representation") or "",
    }


async def send_2fa_code(
    client: httpx.AsyncClient,
    cookie_string: str,
    tokens: dict[str, str],
    account_id: str,
    encrypted_context: str,
    challenge: str = "EMAIL",
    masked_contact_point: str | None = None,
) -> bool:
    """Yêu cầu Facebook gửi mã OTP qua Email hoặc SMS (useTwoStepVerificationSendCodeMutation)."""
    endpoint = "https://accountscenter.facebook.com/api/graphql/"
    friendly_name = "useTwoStepVerificationSendCodeMutation"
    headers = build_common_headers(cookie_string, tokens["lsd"], account_id, friendly_name)

    variables: dict[str, Any] = {
        "encryptedContext": encrypted_context,
        "challenge": challenge,
    }
    if masked_contact_point:
        variables["maskedContactPoint"] = masked_contact_point

    form_data = {
        "av": account_id,
        "__user": account_id,
        "__a": "1",
        "__comet_req": "5",
        "__rev": tokens["revision"],
        "fb_dtsg": tokens["fb_dtsg"],
        "jazoest": calculate_jazoest(tokens["fb_dtsg"]),
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_2FA_SEND_CODE,
    }

    res = await client.post(endpoint, headers=headers, data=form_data)
    data = res.json().get("data") or {}
    return bool(data.get("xfb_two_step_verification_send_notification", {}).get("is_success", False))


async def verify_2fa_challenge(
    client: httpx.AsyncClient,
    cookie_string: str,
    tokens: dict[str, str],
    account_id: str,
    otp_code: str,
    encrypted_context: str,
    method: str = "EMAIL",
    masked_contact_point: str | None = None,
) -> dict[str, Any]:
    """Xác nhận mã bảo mật OTP (2FA) khi hành động đổi tên bị chặn bởi Secured Action.

    Lưu ý quan trọng từ kết quả reverse engineering:
    Sau khi gọi mutation này thành công (is_code_valid: true), Facebook KHÔNG trả về token mới.
    Thay vào đó, trạng thái xác thực bảo mật được gắn trực tiếp vào session cookie của tài khoản
    trên máy chủ Facebook. Chỉ cần gọi lại execute_rename() với cùng tham số là sẽ thành công.
    """
    endpoint = "https://accountscenter.facebook.com/api/graphql/"
    friendly_name = "useTwoFactorLoginValidateCodeMutation"
    headers = build_common_headers(cookie_string, tokens["lsd"], account_id, friendly_name)

    variables: dict[str, Any] = {
        "code": {"sensitive_string_value": otp_code},
        "method": method,
        "flow": "SECURED_ACTION",
        "encryptedContext": encrypted_context,
        "next_uri": None,
        "trust_this_device": None,
    }
    if masked_contact_point:
        variables["maskedContactPoint"] = masked_contact_point

    form_data = {
        "av": account_id,
        "__user": account_id,
        "__a": "1",
        "__comet_req": "5",
        "__rev": tokens["revision"],
        "fb_dtsg": tokens["fb_dtsg"],
        "jazoest": calculate_jazoest(tokens["fb_dtsg"]),
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_2FA_VALIDATE,
    }

    res = await client.post(endpoint, headers=headers, data=form_data)
    return res.json()


def parse_and_print_rename_result(res: dict[str, Any], last_name: str, middle_name: str, first_name: str) -> bool:
    """Đánh giá và in kết quả trả về từ useFXIMUpdateNameMutation."""
    errors = res.get("errors") or []
    data = res.get("data") or {}

    if errors:
        err = errors[0]
        print(f"[-] Đổi tên thất bại: {err.get('message')}")
        print(f"[-] Chi tiết lỗi: {json.dumps(errors, indent=2, ensure_ascii=False)}")
        return False

    update_identity = data.get("fxim_update_identity_name") or {}
    if update_identity.get("error") is None:
        print("\n" + "=" * 65)
        print("✅ ĐỔI TÊN FACEBOOK THÀNH CÔNG!")
        print("=" * 65)
        ui_resp = update_identity.get("ui_response", {})
        legacy_data = (
            ui_resp.get("fx_identity_management", {})
            .get("screen_rules_v2", {})
            .get("name", {})
            .get("legacy_name_data", {})
        )
        if legacy_data:
            print(f"[+] Tên cũ trước đó   : {legacy_data.get('previous_name_full')}")
            print(f"[+] Tên mới đã đổi    : {last_name} {middle_name} {first_name}".strip())
            print(f"[+] Khả năng revert   : {legacy_data.get('can_revert_name')}")
        return True
    else:
        print(f"[-] Kết quả trả về chứa lỗi: {update_identity.get('error')}")
        return False


async def run_rename_flow(
    cookie_string: str,
    first_name: str,
    middle_name: str = "",
    last_name: str = "",
    otp: str | None = None,
    auto_send_otp: bool = True,
    dry_run: bool = False,
) -> None:
    """Quy trình tổng thể thực hiện đổi tên Facebook Accounts Center."""
    print("=" * 65)
    print("   🚀 FACEBOOK ACCOUNTS CENTER - PROFILE NAME CHANGE REPLAY")
    print("=" * 65)

    account_id = extract_account_id(cookie_string)
    if not account_id:
        print("[-] Lỗi: Không thể tìm thấy 'c_user' trong chuỗi Cookie cung cấp!")
        sys.exit(1)

    print(f"[+] Account ID (c_user) : {account_id}")
    print(f"[+] Họ tên mới mục tiêu : First='{first_name}', Middle='{middle_name}', Last='{last_name}'")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Bước 1: Trích xuất tokens bảo mật
        print("[*] Đang truy vấn HTML Accounts Center để trích xuất fb_dtsg & lsd...")
        try:
            tokens = await fetch_tokens_from_page(client, cookie_string, account_id)
            print(f"[+] fb_dtsg  : {tokens['fb_dtsg'][:25]}... (độ dài {len(tokens['fb_dtsg'])})")
            print(f"[+] lsd      : {tokens['lsd']}")
            jazoest = calculate_jazoest(tokens["fb_dtsg"])
            print(f"[+] jazoest  : {jazoest} (tính toán tự động)")
        except Exception as e:
            print(f"[!] Cảnh báo khi crawl tokens từ trang: {e}")
            print("[*] Sử dụng fallback tokens từ session task_b528f651...")
            tokens = {
                "fb_dtsg": "NAfwSF43yFdW2PxSeGWYiFpeWfYF4MYcG6Yap88lNJAL7dCxDXK2pHQ:42:1790242273",
                "lsd": "zCqJoMpmeaHmvrUSYVru8s",
                "revision": "1048361770",
            }

        # Bước 2: Kiểm tra tính hợp lệ của tên mới
        print("[*] Đang gửi kiểm tra useFXIMNameValidatorQuery...")
        val_res = await validate_name(client, cookie_string, tokens, account_id, first_name, middle_name, last_name)
        val_err = val_res.get("errors")
        if val_err:
            print(f"[!] Cảnh báo xác thực tên: {json.dumps(val_err, ensure_ascii=False)}")
        else:
            print("[+] Tên hợp lệ theo chính sách của Facebook.")

        if dry_run:
            print("[*] Chế độ DRY-RUN: Dừng trước khi thực thi mutation cập nhật tên.")
            return

        # Bước 3: Gửi mutation cập nhật tên lần 1
        print("[*] Đang gửi useFXIMUpdateNameMutation (DocID: 9538143859625836)...")
        mut_res = await execute_rename(client, cookie_string, tokens, account_id, first_name, middle_name, last_name)

        # Bước 4: Đánh giá kết quả lần 1 & nhận diện 2FA Challenge
        errors = mut_res.get("errors") or []
        if errors:
            err = errors[0]
            summary = err.get("summary")
            desc = err.get("description", "")
            code = err.get("code")

            # DẤU HIỆU NHẬN DIỆN CÁN 2FA:
            # 1. summary == "Secured Action"
            # 2. code == 2136001
            # 3. description chứa JSON có challenge_type (vd: "reauth") và encrypted_context
            if summary == "Secured Action" or "challenge_type" in desc:
                print("\n" + "=" * 65)
                print("🔒 PHÁT HIỆN YÊU CẦU XÁC THỰC BẢO MẬT (SECURED ACTION / 2FA REAUTH)")
                print("=" * 65)
                print(f"[!] Facebook yêu cầu xác thực 2FA trước khi cho phép lưu tên mới.")
                print(f"[!] Mã lỗi Facebook: Code={code}, Summary='{summary}'")

                try:
                    challenge_info = json.loads(desc)
                except Exception:
                    challenge_info = {}

                encrypted_context = challenge_info.get("encrypted_context", "")
                if not encrypted_context:
                    print("[-] Không thể trích xuất encrypted_context từ error response!")
                    return

                print(f"[*] Challenge Type    : {challenge_info.get('challenge_type', 'reauth')}")
                print(f"[*] Encrypted Context : {encrypted_context[:50]}...")

                # Truy vấn phương thức xác thực và địa chỉ email/sđt nhận mã
                print("[*] Đang truy vấn phương thức 2FA của tài khoản qua TwoStepVerificationRootQuery...")
                method_info = await query_2fa_default_method(client, cookie_string, tokens, account_id, encrypted_context)
                method = method_info.get("method") or "EMAIL"
                masked_contact = method_info.get("representation") or ""
                print(f"[+] Phương thức nhận mã : {method}")
                if masked_contact:
                    print(f"[+] Địa chỉ nhận OTP    : {masked_contact}")

                otp_code = otp
                if not otp_code:
                    if auto_send_otp:
                        print(f"[*] Đang yêu cầu Facebook gửi mã OTP đến {masked_contact or method}...")
                        sent = await send_2fa_code(
                            client, cookie_string, tokens, account_id, encrypted_context, method, masked_contact
                        )
                        if sent:
                            print("[+] Mã xác thực OTP đã được gửi đi thành công!")
                        else:
                            print("[!] Gửi OTP không thành công hoặc mã trước đó vẫn còn hiệu lực.")

                    try:
                        otp_code = input("\n>> Nhập mã xác thực OTP nhận được (6-8 chữ số): ").strip()
                    except EOFError:
                        print("[-] Môi trường không tương tác (non-interactive). Hãy truyền --otp <MÃ_OTP>.")
                        return

                if not otp_code:
                    print("[-] Chưa có mã OTP, hủy thao tác đổi tên.")
                    return

                # Bước 5: Xác minh mã 2FA Challenge qua useTwoFactorLoginValidateCodeMutation
                print(f"[*] Đang xác minh mã OTP '{otp_code}'...")
                val_2fa_res = await verify_2fa_challenge(
                    client,
                    cookie_string,
                    tokens,
                    account_id,
                    otp_code,
                    encrypted_context,
                    method=method,
                    masked_contact_point=masked_contact,
                )

                val_data = val_2fa_res.get("data") or {}
                code_val_info = val_data.get("xfb_two_factor_login_validate_code") or {}
                if not code_val_info.get("is_code_valid"):
                    err_msg = code_val_info.get("error_message") or val_2fa_res.get("errors")
                    print(f"[-] Xác minh OTP thất bại! Lỗi: {err_msg}")
                    return

                print("\n" + "=" * 65)
                print("🔑 XÁC MINH 2FA THÀNH CÔNG!")
                print("=" * 65)
                print("[*] Giải thích kỹ thuật: Facebook ghi nhận trạng thái đã vượt qua 2FA")
                print("    trực tiếp trên Session Cookie của Server (server-side authentication).")
                print("[*] KHÔNG CẦN đính kèm token mới. Tiến hành tự động gọi lại execute_rename()...")

                # Bước 6: Tự động gọi lại execute_rename với cùng tham số
                mut_res_2 = await execute_rename(
                    client, cookie_string, tokens, account_id, first_name, middle_name, last_name
                )
                parse_and_print_rename_result(mut_res_2, last_name, middle_name, first_name)
                return
            else:
                print(f"[-] Đổi tên thất bại: {err.get('message')}")
                print(f"[-] Chi tiết lỗi: {json.dumps(errors, indent=2, ensure_ascii=False)}")
                return

        # Nếu không dính 2FA, hiển thị kết quả ngay
        parse_and_print_rename_result(mut_res, last_name, middle_name, first_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tái hiện chuỗi API đổi tên Facebook Accounts Center qua Cookie")
    parser.add_argument("--first-name", "-f", default="Nguyễn", help="First name (mặc định: Nguyễn)")
    parser.add_argument("--middle-name", "-m", default="Văn", help="Middle name (mặc định: Văn)")
    parser.add_argument("--last-name", "-l", default="Dũng", help="Last name (mặc định: Dũng)")
    parser.add_argument("--cookie", "-c", default=DEFAULT_COOKIE, help="Chuỗi Cookie Facebook đầy đủ (có c_user, xs...)")
    parser.add_argument("--otp", default=None, help="Mã xác thực 2FA (OTP) nếu đã nhận được trước đó")
    parser.add_argument("--no-send-otp", action="store_true", help="Không tự động kích hoạt gửi lại mã OTP mới qua email/SMS")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra token & validate, không gửi mutation đổi tên thật")

    args = parser.parse_args()

    asyncio.run(
        run_rename_flow(
            cookie_string=args.cookie,
            first_name=args.first_name,
            middle_name=args.middle_name,
            last_name=args.last_name,
            otp=args.otp,
            auto_send_otp=not args.no_send_otp,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
