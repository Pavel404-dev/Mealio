"""PostgreSQL lifecycle for ingredient allergen verification revocation."""

REVOKE_FUNCTION = """
CREATE FUNCTION public.revoke_ingredient_allergen_verifications_v1()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM public.ingredient_allergen_verifications WHERE ingredient_id = OLD.id;
    RETURN NULL;
END;
$$
"""

REVOKE_TRIGGER = """
CREATE TRIGGER revoke_ingredient_allergen_verifications_v1
AFTER UPDATE OF name, category ON public.ingredients
FOR EACH ROW
WHEN (OLD.name IS DISTINCT FROM NEW.name OR OLD.category IS DISTINCT FROM NEW.category)
EXECUTE FUNCTION public.revoke_ingredient_allergen_verifications_v1()
"""

DROP_REVOKE_TRIGGER = """
DROP TRIGGER revoke_ingredient_allergen_verifications_v1 ON public.ingredients
"""

DROP_REVOKE_FUNCTION = """
DROP FUNCTION public.revoke_ingredient_allergen_verifications_v1()
"""
