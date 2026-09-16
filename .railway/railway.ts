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
      // Create these shared staging values before the first apply.
      JWT_SECRET_KEY: ctx.shared.JWT_SECRET_KEY,
      EMAIL_OTP_PEPPER: ctx.shared.EMAIL_OTP_PEPPER,
      AUTH_ABUSE_PEPPER: ctx.shared.AUTH_ABUSE_PEPPER,
      MAILTRAP_API_TOKEN: ctx.shared.MAILTRAP_API_TOKEN,
      MAILTRAP_SANDBOX_ID: ctx.shared.MAILTRAP_SANDBOX_ID,
      SMTP_FROM_EMAIL: ctx.shared.SMTP_FROM_EMAIL,
      EMAIL_VERIFICATION_URL_BASE:
        ctx.shared.EMAIL_VERIFICATION_URL_BASE,
    },
  });

  return project("mealio-staging", { resources: [db, backend] });
});
