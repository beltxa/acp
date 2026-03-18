// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use std::path::PathBuf;

use acp_runtime::capabilities::AgentCapabilities;
use acp_runtime::identity::{AgentIdentity, parse_agent_id, read_identity, write_identity};
use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "acp-rs", about = "ACP Rust CLI", version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    Identity(IdentityCommands),
}

#[derive(Parser, Debug)]
struct IdentityCommands {
    #[command(subcommand)]
    command: IdentitySubcommand,
}

#[derive(Subcommand, Debug)]
enum IdentitySubcommand {
    Parse {
        #[arg(long)]
        agent_id: String,
    },
    Show {
        #[arg(long)]
        agent_id: String,
        #[arg(long, default_value = ".acp-data")]
        storage_dir: PathBuf,
    },
    Create {
        #[arg(long)]
        agent_id: String,
        #[arg(long, default_value = ".acp-data")]
        storage_dir: PathBuf,
        #[arg(long)]
        direct_endpoint: Option<String>,
        #[arg(long = "relay-hint")]
        relay_hints: Vec<String>,
        #[arg(long, default_value = "self_asserted")]
        trust_profile: String,
        #[arg(long, default_value_t = 365)]
        valid_days: i64,
    },
}

fn main() {
    let cli = Cli::parse();
    let result = match cli.command {
        Commands::Identity(identity) => run_identity(identity),
    };
    if let Err(err) = result {
        eprintln!("{err}");
        std::process::exit(1);
    }
}

fn run_identity(cmds: IdentityCommands) -> Result<(), String> {
    match cmds.command {
        IdentitySubcommand::Parse { agent_id } => {
            let parsed = parse_agent_id(&agent_id).map_err(|err| err.to_string())?;
            println!(
                "{}",
                serde_json::json!({
                    "agent_id": agent_id,
                    "name": parsed.name,
                    "domain": parsed.domain,
                })
            );
            Ok(())
        }
        IdentitySubcommand::Show {
            agent_id,
            storage_dir,
        } => {
            let Some(bundle) =
                read_identity(&storage_dir, &agent_id).map_err(|err| err.to_string())?
            else {
                return Err(format!(
                    "identity not found for {agent_id} in {}",
                    storage_dir.display()
                ));
            };
            println!(
                "{}",
                serde_json::json!({
                    "agent_id": bundle.identity.agent_id,
                    "storage_dir": storage_dir,
                    "trust_profile": bundle.identity_document.get("trust_profile"),
                    "service": bundle.identity_document.get("service"),
                    "valid_until": bundle.identity_document.get("valid_until"),
                })
            );
            Ok(())
        }
        IdentitySubcommand::Create {
            agent_id,
            storage_dir,
            direct_endpoint,
            relay_hints,
            trust_profile,
            valid_days,
        } => {
            let identity = AgentIdentity::create(&agent_id).map_err(|err| err.to_string())?;
            let capabilities = AgentCapabilities::new(agent_id.as_str()).to_map();
            let identity_doc = identity
                .build_identity_document(
                    direct_endpoint.as_deref(),
                    &relay_hints,
                    &trust_profile,
                    Some(&capabilities),
                    valid_days,
                    None,
                    None,
                    None,
                    None,
                )
                .map_err(|err| err.to_string())?;
            write_identity(&storage_dir, &identity, &identity_doc)
                .map_err(|err| err.to_string())?;
            println!(
                "{}",
                serde_json::json!({
                    "ok": true,
                    "agent_id": agent_id,
                    "storage_dir": storage_dir,
                    "identity_path": acp_runtime::identity::identity_path(&storage_dir, &identity.agent_id),
                    "trust_profile": trust_profile,
                })
            );
            Ok(())
        }
    }
}
