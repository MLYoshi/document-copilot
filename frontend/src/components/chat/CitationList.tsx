// Collapsible source list shown under assistant answers — the product's
// trust core. Renders full passages when available (live stream), falling
// back to quote pointers for history messages (the backend persists only
// chunk_id + quote, never re-fetched passages).
import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import type { Citation, SourcePassage } from "@/chat/types";
import { cn } from "@/lib/utils";

type CitationListProps = {
  passages: SourcePassage[];
  pointers: Citation[];
};

function PassageCard({
  passage,
  ordinal,
}: {
  passage: SourcePassage;
  ordinal: number;
}) {
  return (
    <div className="rounded-lg border bg-card p-4 text-sm shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">
          [{ordinal}] {passage.title}
        </span>
        {passage.ticker ? (
          <Badge variant="secondary">{passage.ticker}</Badge>
        ) : null}
        {passage.form ? <Badge variant="outline">{passage.form}</Badge> : null}
        {passage.filing_date ? (
          <Badge variant="outline">{passage.filing_date}</Badge>
        ) : null}
      </div>
      {passage.section_path ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {passage.section_path}
        </p>
      ) : null}
      <blockquote className="mt-3 border-l-2 pl-3 italic text-muted-foreground">
        {passage.content}
      </blockquote>
      {passage.quote ? (
        <p className="mt-2 rounded bg-amber-100 px-2 py-1 text-xs text-amber-900">
          <span className="font-medium">原文引用：</span>
          {passage.quote}
        </p>
      ) : null}
      {passage.source_url ? (
        <a
          href={passage.source_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
        >
          查看原文 (SEC EDGAR)
          <ExternalLink className="size-3" />
        </a>
      ) : null}
    </div>
  );
}

function PointerCard({ pointer }: { pointer: Citation }) {
  return (
    <div className="rounded-lg border bg-card p-4 text-sm shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">[{pointer.ordinal}] 来源段落</span>
      </div>
      {pointer.quote ? (
        <blockquote className="mt-3 border-l-2 pl-3 italic text-muted-foreground">
          {pointer.quote}
        </blockquote>
      ) : null}
      <p className="mt-2 text-xs text-muted-foreground">
        历史消息仅保留引用指针，重新提问可获取完整原文。
      </p>
    </div>
  );
}

export function CitationList({ passages, pointers }: CitationListProps) {
  const [open, setOpen] = useState(false);
  if (passages.length === 0 && pointers.length === 0) return null;
  const count = passages.length + pointers.length;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-3">
      <CollapsibleTrigger
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-muted-foreground",
          "hover:bg-accent hover:text-accent-foreground"
        )}
      >
        引用来源 [{count}]
        <ChevronDown
          className={cn("size-4 transition-transform", open && "rotate-180")}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <Separator className="my-3" />
        <div className="space-y-3">
          {passages.map((passage, index) => (
            <PassageCard key={passage.chunk_id} passage={passage} ordinal={index + 1} />
          ))}
          {pointers.map((pointer) => (
            <PointerCard key={pointer.chunk_id} pointer={pointer} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
