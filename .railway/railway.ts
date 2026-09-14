import { defineRailway, github, postgres, project, service } from "railway/iac";

export default defineRailway((ctx) => {
  if (ctx.environment !== "staging") {
    throw new Error("Mealio infrastructure may only target the staging environment.");
  }

  const db = postgres("Postgres");

  const backend = service("backend", {
    source: github("Pavel404-dev/Mealio", {
      branch: "main",
      rootDirectory: "backend",
    }),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
    },
    preDeploy: "alembic upgrade head",
    healthcheck: "/health/db",
    healthcheckTimeout: 120,
    replicas: 1,
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
    },
    env: {
      // Railway resolves these references; no database credentials are read locally.
      DATABASE_URL:
        "postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}",
      // Create these independent shared secrets in staging before the first apply.
      JWT_SECRET_KEY: ctx.shared.JWT_SECRET_KEY,
      EMAIL_OTP_PEPPER: ctx.shared.EMAIL_OTP_PEPPER,
      AUTH_ABUSE_PEPPER: ctx.shared.AUTH_ABUSE_PEPPER,
    },
  });

  return project("mealio-staging", { resources: [db, backend] });
});
