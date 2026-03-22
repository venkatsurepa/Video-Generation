import pg from "pg";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const { Client } = pg;

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATIONS_DIR = path.join(__dirname, "supabase", "migrations");

// Connection string from user ($ doesn't need encoding in most drivers)
const CONN_STRING =
  "postgresql://postgres:GirthBrooks123$@db.qflkctgemkwochgkzqzj.supabase.co:5432/postgres";

// Extensions that may need to be created before migrations can run
const EXTENSION_PATTERN = /extension\s+"?(\w+)"?\s+(?:does not exist|is not available)/i;
const KNOWN_EXTENSIONS = ["pg_cron", "pg_net", "pgsodium", "pgmq", "pg_trgm", "pgcrypto"];

async function main() {
  const files = fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  console.log(`Found ${files.length} migration files\n`);

  const client = new Client({ connectionString: CONN_STRING });
  console.log("Connecting to database...");
  await client.connect();
  console.log("Connected!\n");

  for (const filename of files) {
    const filepath = path.join(MIGRATIONS_DIR, filename);
    console.log(`--- Running: ${filename} ---`);
    const sql = fs.readFileSync(filepath, "utf-8");

    try {
      await client.query(sql);
      console.log(`  SUCCESS\n`);
    } catch (e) {
      console.log(`  FAILED: ${e.message}`);

      // Check if the error is about a missing extension
      const extMatch = e.message.match(EXTENSION_PATTERN);
      const mentionedExt = KNOWN_EXTENSIONS.find((ext) =>
        e.message.toLowerCase().includes(ext)
      );
      const extName = extMatch?.[1] || mentionedExt;

      if (extName) {
        console.log(`  >> Attempting: CREATE EXTENSION IF NOT EXISTS ${extName};`);
        try {
          await client.query(`CREATE EXTENSION IF NOT EXISTS "${extName}";`);
          console.log(`  >> Extension ${extName} created. Retrying migration...`);
          try {
            await client.query(sql);
            console.log(`  SUCCESS (after creating extension)\n`);
            continue;
          } catch (e2) {
            console.log(`  FAILED on retry: ${e2.message}\n`);
          }
        } catch (extErr) {
          console.log(`  >> Extension creation failed: ${extErr.message}\n`);
        }
      }

      console.log("\nSTOPPING — fix the error above before continuing.");
      await client.end();
      process.exit(1);
    }
  }

  // Verification
  console.log("=".repeat(60));
  console.log("VERIFICATION");
  console.log("=".repeat(60));

  console.log("\n--- Public tables ---");
  const tables = await client.query(
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
  );
  for (const r of tables.rows) {
    console.log(`  ${r.tablename}`);
  }
  console.log(`\nTotal public tables: ${tables.rows.length}`);

  await client.end();
}

main().catch((e) => {
  console.error("Fatal:", e.message);
  process.exit(1);
});
