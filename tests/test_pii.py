from app.services.pii import mask_pii


def test_masks_aadhaar_with_and_without_spaces():
    result = mask_pii("Aadhaar 2345 6789 0123 and 987654321098")
    assert "2345" not in result.text
    assert "987654321098" not in result.text
    assert result.found["AADHAAR"] == 2


def test_masks_indian_phone_numbers():
    result = mask_pii("Call me on +91 98765 43210 or 9123456789")
    assert "98765" not in result.text and "9123456789" not in result.text
    assert result.found["PHONE"] == 2


def test_masks_pan_email_upi_and_card():
    text = "PAN ABCDE1234F, mail a.b@gmail.com, UPI ravi@okaxis, card 4111 1111 1111 1111"
    result = mask_pii(text)
    for secret in ("ABCDE1234F", "a.b@gmail.com", "ravi@okaxis", "4111"):
        assert secret not in result.text
    assert {"PAN", "EMAIL", "UPI_ID", "CARD"} <= set(result.found)


def test_masks_bank_account_number():
    result = mask_pii("Credit to A/c No: 123456789012345")
    assert "123456789012345" not in result.text


def test_leaves_ordinary_text_and_amounts_alone():
    text = "Penalty of Rs 500 on 12/10/2026 for late delivery of order 4521"
    result = mask_pii(text)
    assert result.text == text
    assert not result.masked_anything
