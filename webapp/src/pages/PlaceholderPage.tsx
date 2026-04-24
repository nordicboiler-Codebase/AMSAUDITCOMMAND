import { Wrench } from "lucide-react";
import { EmptyState, PageHeader } from "@/components/ui/page";

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <EmptyState
        icon={<Wrench className="h-5 w-5" />}
        title="Coming soon to the new UI"
        description="This page is wired to the FastAPI backend but doesn't have a rich React view yet. The underlying API is fully functional — use /docs for now."
      />
    </>
  );
}
