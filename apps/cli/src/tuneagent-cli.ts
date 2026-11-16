#!/usr/bin/env node
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repositoryRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../..',
)

function resolvePython(): string {
  const configuredPython = process.env.TUNEAGENT_PYTHON?.trim()
  if (configuredPython) {
    if (!existsSync(configuredPython)) {
      throw new Error(`TUNEAGENT_PYTHON does not exist: ${configuredPython}`)
    }
    return configuredPython
  }

  const venvPython = join(repositoryRoot, '.venv', 'bin', 'python')
  if (existsSync(venvPython)) {
    return venvPython
  }
  return 'python3'
}

async function runSearch(args: readonly string[]): Promise<number> {
  const python = resolvePython()
  const script = join(repositoryRoot, 'scripts', 'run_cli.py')

  return await new Promise<number>((resolveCode, reject) => {
    const child = spawn(python, [script, ...args], {
      cwd: repositoryRoot,
      env: process.env,
      stdio: 'inherit',
    })
    child.once('error', reject)
    child.once('exit', (code, signal) => {
      if (signal) {
        console.error(`TuneAgent Python process terminated by ${signal}`)
        resolveCode(1)
        return
      }
      resolveCode(code ?? 1)
    })
  })
}

async function main(): Promise<number> {
  const [command, ...args] = process.argv.slice(2)
  if (command !== 'search') {
    console.error('Usage: pnpm cli search "<natural-language request>" [options]')
    return 2
  }
  return await runSearch(args)
}

try {
  process.exitCode = await main()
} catch (error) {
  const message = error instanceof Error ? error.message : String(error)
  console.error(`tuneagent-cli: ${message}`)
  process.exitCode = 1
}
