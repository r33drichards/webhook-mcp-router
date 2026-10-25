// Credential-free runner contract probe. No environment values or body bytes logged.
use std::io::{self, Read, Write};
fn main() {
    let has = |name: &str| std::env::var_os(name).is_some();
    // Emit metadata before touching stdin: a wrongly selected server runner may
    // keep stdin open indefinitely. Never wait for EOF without a length.
    eprintln!("CGI_ENVELOPE_START request_method_present={} content_length_present={}", has("REQUEST_METHOD"), has("CONTENT_LENGTH"));
    let length = std::env::var("CONTENT_LENGTH").ok().and_then(|v| v.parse::<usize>().ok()).filter(|n| *n <= 64);
    let mut body = vec![0; length.unwrap_or(0)];
    let read_ok = match length {
        Some(0) => true,
        Some(_) => io::stdin().read_exact(&mut body).is_ok(),
        None => false,
    };
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
