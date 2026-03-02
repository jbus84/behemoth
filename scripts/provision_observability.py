import os
import re
from pathlib import Path

def provision_alertmanager():
    template_path = Path("alertmanager.yml.template")
    output_path = Path("alertmanager.yml")
    env_path = Path(".env")

    if not template_path.exists():
        print(f"❌ Template not found at {template_path}")
        return

    # Load .env if it exists
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    env_vars[key] = value

    # Prefer actual environment variables
    env_vars.update(os.environ)

    with open(template_path, "r") as f:
        content = f.read()

    # Simple regex substitution for ${VAR}
    def replace_var(match):
        var_name = match.group(1)
        return env_vars.get(var_name, match.group(0))

    new_content = re.sub(r"\$\{([^}]+)\}", replace_var, content)

    with open(output_path, "w") as f:
        f.write(new_content)

    print(f"✅ Alertmanager configuration provisioned to {output_path}")

if __name__ == "__main__":
    provision_alertmanager()
