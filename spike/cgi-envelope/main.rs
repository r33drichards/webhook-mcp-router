// Credential-free runner contract probe. No environment values or body bytes logged.
use std::io::{self, Read, Write};
fn main() {
    let has = |name: &str| std::env::var_os(name).is_some();
    let mut body = Vec::new();
    let read_ok = io::stdin().take(65).read_to_end(&mut body).is_ok();
    let method = std::env::var("REQUEST_METHOD").unwrap_or_default();
    let report = format!(concat!("{{\"request_method_present\":{},\"method_is_get\":{},\"method_is_post\":{},",
        "\"script_name_present\":{},\"server_protocol_present\":{},\"gateway_interface_present\":{},",
        "\"content_length_present\":{},\"stdin_read_ok\":{},\"stdin_empty\":{},\"stdin_synthetic\":{}}}"),
        has("REQUEST_METHOD"), method == "GET", method == "POST", has("SCRIPT_NAME"),
        has("SERVER_PROTOCOL"), has("GATEWAY_INTERFACE"), has("CONTENT_LENGTH"), read_ok,
        body.is_empty(), body == b"Synthetic");
    eprintln!("CGI_ENVELOPE_PROBE {}", report);
    let response = format!("Status: 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nContent-Length: {}\r\n\r\n{}", report.len(), report);
    let _ = io::stdout().write_all(response.as_bytes());
}
