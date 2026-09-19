import { Card } from "./ui";

function Bar({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-slate-200 ${className}`} />;
}

export function MatchCardSkeleton() {
  return (
    <Card className="p-5">
      <div className="flex items-start gap-4">
        <div className="h-12 w-12 animate-pulse rounded-full bg-slate-200" />
        <div className="flex-1 space-y-2">
          <Bar className="h-4 w-40" />
          <Bar className="h-3 w-64" />
          <div className="flex gap-1.5 pt-1">
            <Bar className="h-5 w-20" />
            <Bar className="h-5 w-24" />
            <Bar className="h-5 w-16" />
          </div>
        </div>
        <div className="h-14 w-14 animate-pulse rounded-full bg-slate-200" />
      </div>
      <div className="mt-4 space-y-2">
        <Bar className="h-3 w-3/4" />
        <Bar className="h-3 w-2/3" />
        <Bar className="h-3 w-1/2" />
      </div>
    </Card>
  );
}

export function TeacherCardSkeleton() {
  return (
    <Card className="p-4">
      <div className="flex gap-3">
        <div className="h-10 w-10 animate-pulse rounded-full bg-slate-200" />
        <div className="flex-1 space-y-2">
          <Bar className="h-4 w-32" />
          <Bar className="h-3 w-48" />
          <Bar className="h-3 w-40" />
        </div>
      </div>
    </Card>
  );
}
