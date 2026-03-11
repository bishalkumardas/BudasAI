-- Production hardening for BudasAI Supabase DB
-- Run this in Supabase SQL Editor (or via migration runner with write access)

-- 1) Enable RLS on workflow tables
ALTER TABLE public.premium_workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.premium_workflow_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.premium_workflow_results ENABLE ROW LEVEL SECURITY;

-- 2) Remove insecure/overly broad write policies
DROP POLICY IF EXISTS "Allow insert from backend" ON public.blogs;
DROP POLICY IF EXISTS "Allow update from backend" ON public.blogs;
DROP POLICY IF EXISTS "Allow insert from backend" ON public.stories;
DROP POLICY IF EXISTS "Allow update from backend" ON public.stories;
DROP POLICY IF EXISTS "Admin can manage user profiles" ON public.user_profiles;

-- 3) Recreate policies with safer scopes and better auth call patterns
DROP POLICY IF EXISTS "Authenticated users can manage pricing plans" ON public.pricing_plans;
CREATE POLICY "Authenticated users can manage pricing plans"
ON public.pricing_plans
FOR ALL
TO authenticated
USING ((SELECT auth.uid()) IS NOT NULL)
WITH CHECK ((SELECT auth.uid()) IS NOT NULL);

DROP POLICY IF EXISTS "Users can read own profile" ON public.user_profiles;
CREATE POLICY "Users can read own profile"
ON public.user_profiles
FOR SELECT
TO authenticated
USING (((SELECT auth.uid()) = auth_user_id));

DROP POLICY IF EXISTS "Users can update own profile" ON public.user_profiles;
CREATE POLICY "Users can update own profile"
ON public.user_profiles
FOR UPDATE
TO authenticated
USING (((SELECT auth.uid()) = auth_user_id))
WITH CHECK (((SELECT auth.uid()) = auth_user_id));

DROP POLICY IF EXISTS "Users can read own billing records" ON public.billing_records;
CREATE POLICY "Users can read own billing records"
ON public.billing_records
FOR SELECT
TO authenticated
USING (((SELECT auth.uid())::text = (user_id)::text));

-- 4) Leads policy (RLS already enabled, add explicit policy)
DROP POLICY IF EXISTS "Public can submit leads" ON public.leads;
CREATE POLICY "Public can submit leads"
ON public.leads
FOR INSERT
TO anon, authenticated
WITH CHECK (
  email IS NOT NULL
  AND position('@' in email) > 1
  AND coalesce(length(name), 0) > 0
);

-- 5) Premium workflow policies
DROP POLICY IF EXISTS "Public can read published premium workflows" ON public.premium_workflows;
CREATE POLICY "Public can read published premium workflows"
ON public.premium_workflows
FOR SELECT
TO anon, authenticated
USING (is_published = true);

DROP POLICY IF EXISTS "Authenticated users can manage premium workflows" ON public.premium_workflows;
CREATE POLICY "Authenticated users can manage premium workflows"
ON public.premium_workflows
FOR ALL
TO authenticated
USING ((SELECT auth.uid()) IS NOT NULL)
WITH CHECK ((SELECT auth.uid()) IS NOT NULL);

DROP POLICY IF EXISTS "Public can read published premium workflow steps" ON public.premium_workflow_steps;
CREATE POLICY "Public can read published premium workflow steps"
ON public.premium_workflow_steps
FOR SELECT
TO anon, authenticated
USING (
  EXISTS (
    SELECT 1
    FROM public.premium_workflows w
    WHERE w.id = premium_workflow_steps.workflow_id
      AND w.is_published = true
  )
);

DROP POLICY IF EXISTS "Authenticated users can manage premium workflow steps" ON public.premium_workflow_steps;
CREATE POLICY "Authenticated users can manage premium workflow steps"
ON public.premium_workflow_steps
FOR ALL
TO authenticated
USING ((SELECT auth.uid()) IS NOT NULL)
WITH CHECK ((SELECT auth.uid()) IS NOT NULL);

DROP POLICY IF EXISTS "Public can read published premium workflow results" ON public.premium_workflow_results;
CREATE POLICY "Public can read published premium workflow results"
ON public.premium_workflow_results
FOR SELECT
TO anon, authenticated
USING (
  EXISTS (
    SELECT 1
    FROM public.premium_workflows w
    WHERE w.id = premium_workflow_results.workflow_id
      AND w.is_published = true
  )
);

DROP POLICY IF EXISTS "Authenticated users can manage premium workflow results" ON public.premium_workflow_results;
CREATE POLICY "Authenticated users can manage premium workflow results"
ON public.premium_workflow_results
FOR ALL
TO authenticated
USING ((SELECT auth.uid()) IS NOT NULL)
WITH CHECK ((SELECT auth.uid()) IS NOT NULL);

-- 6) Add missing FK indexes for performance
CREATE INDEX IF NOT EXISTS idx_premium_workflows_pricing_plan_id
  ON public.premium_workflows(pricing_plan_id);

CREATE INDEX IF NOT EXISTS idx_premium_workflow_steps_workflow_id
  ON public.premium_workflow_steps(workflow_id);

CREATE INDEX IF NOT EXISTS idx_premium_workflow_results_workflow_id
  ON public.premium_workflow_results(workflow_id);
