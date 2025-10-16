use anyhow::{anyhow, Result};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

const BASE: &str = "https://gspfonqp30.execute-api.us-east-2.amazonaws.com";

#[derive(Serialize)]
struct PostCred<'a> {
    username: &'a str,
    service:  &'a str,
    password: &'a str,
}

#[derive(Deserialize, Debug)]
struct PostResp { ok: bool, username: String, service: String }

#[derive(Deserialize, Debug)]
struct ListResp {
    username: String,
    services: HashMap<String, ServiceInfo>,
}
#[derive(Deserialize, Debug)]
struct ServiceInfo { username: Option<String> }

#[derive(Deserialize, Debug)]
struct OneCredResp {
    username: String,
    service: String,
    #[serde(default)] password: String,
}

fn add_cred(c: &Client, u: &str, s: &str, p: &str) -> Result<PostResp> {
    let r = c.post(format!("{BASE}/creds"))
        .json(&PostCred { username: u, service: s, password: p })
        .send()?;
    if !r.status().is_success() { return Err(anyhow!("POST failed: {} {}", r.status(), r.text()?)); }
    Ok(r.json()?)
}
fn list_services(c: &Client, u: &str) -> Result<ListResp> {
    let r = c.get(format!("{BASE}/creds")).query(&[("username", u)]).send()?;
    if !r.status().is_success() { return Err(anyhow!("LIST failed: {} {}", r.status(), r.text()?)); }
    Ok(r.json()?)
}
fn get_one(c: &Client, u: &str, s: &str) -> Result<OneCredResp> {
    let r = c.get(format!("{BASE}/creds/{s}")).query(&[("username", u)]).send()?;
    if !r.status().is_success() { return Err(anyhow!("GET one failed: {} {}", r.status(), r.text()?)); }
    Ok(r.json()?)
}

fn main() -> Result<()> {
    let client = Client::new();

    // demo: add → list → get one
    println!("adding…");
    let add = add_cred(&client, "Mattd", "github", "password123")?;
    println!("added: {:?}", add);

    println!("listing…");
    let list = list_services(&client, "Mattd")?;
    println!("services: {:?}", list.services);

    println!("fetching one…");
    let one = get_one(&client, "Mattd", "github")?;
    println!("credential: {:?}", one);

    Ok(())
}

