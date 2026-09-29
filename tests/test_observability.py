from app.observability import endpoint_label


def test_endpoint_label_removes_credentials_path_and_query() -> None:
    label = endpoint_label(
        "https://user:secret@example.org:8443/api/interpreter?token=hidden"
    )

    assert label == "example.org:8443"
    assert "secret" not in label
    assert "token" not in label


def test_endpoint_label_handles_invalid_url_without_echoing_input() -> None:
    assert endpoint_label("not a url with secret=abc") == "invalid-endpoint"
