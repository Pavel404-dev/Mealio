import assert from "node:assert/strict";
import test from "node:test";
import { createRailwayContext, project } from "railway/iac";
import railwayProgram from "./railway.ts";

test("staging evaluates offline to the intended project graph", async () => {
  const definition = await railwayProgram(
    createRailwayContext({ environment: "staging" }),
    project,
  );

  assert.deepEqual(definition, {
    name: "mealio-staging",
    resources: [
      {
        address: "database.Postgres",
        type: "database",
        kind: "database",
        engine: "postgres",
        name: "Postgres",
        image: "ghcr.io/railwayapp-templates/postgres-ssl:18",
        output: "DATABASE_URL",
        defaultMountPath: "/var/lib/postgresql/data",
        source: {
          type: "image",
          image: "ghcr.io/railwayapp-templates/postgres-ssl:18",
        },
      },
      {
        address: "service.backend",
        type: "service",
        kind: "github",
        name: "backend",
        source: {
          type: "github",
          repo: "Pavel404-dev/Mealio",
          branch: "main",
          rootDirectory: "backend",
        },
        build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
        deploy: {
          preDeployCommand: ["alembic upgrade head"],
          healthcheckPath: "/health/db",
          healthcheckTimeout: 120,
          numReplicas: 1,
          restartPolicyType: "ON_FAILURE",
          restartPolicyMaxRetries: 5,
        },
        variables: {
          DATABASE_URL: {
            type: "literal",
            value:
              "postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}",
          },
          JWT_SECRET_KEY: { type: "sharedReference", name: "JWT_SECRET_KEY" },
          EMAIL_OTP_PEPPER: { type: "sharedReference", name: "EMAIL_OTP_PEPPER" },
          AUTH_ABUSE_PEPPER: { type: "sharedReference", name: "AUTH_ABUSE_PEPPER" },
        },
      },
    ],
  });
});

for (const environment of ["production", "development", "Staging", undefined]) {
  test(`rejects environment ${environment ?? "<unset>"}`, async () => {
    await assert.rejects(
      async () => railwayProgram(createRailwayContext({ environment }), project),
      /Mealio infrastructure may only target the staging environment\./,
    );
  });
}
