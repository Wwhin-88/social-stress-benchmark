"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { Check, Minus } from "lucide-react"

function Checkbox({
  className,
  checked,
  indeterminate,
  onCheckedChange,
  ...props
}: React.ComponentProps<"button"> & {
  checked?: boolean
  indeterminate?: boolean
  onCheckedChange?: (checked: boolean) => void
}) {
  const inputRef = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => {
    if (inputRef.current) {
      inputRef.current.indeterminate = !!indeterminate
    }
  }, [indeterminate])

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      data-slot="checkbox"
      data-state={indeterminate ? "indeterminate" : checked ? "checked" : "unchecked"}
      className={cn(
        "peer inline-flex size-4 shrink-0 items-center justify-center rounded-sm border border-input",
        "ring-offset-background transition-colors",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked || indeterminate
          ? "bg-primary border-primary text-primary-foreground"
          : "bg-transparent",
        className
      )}
      onClick={() => onCheckedChange?.(!checked)}
      {...props}
    >
      <input ref={inputRef} type="checkbox" className="sr-only" checked={checked} readOnly />
      {indeterminate ? (
        <Minus className="size-3" />
      ) : checked ? (
        <Check className="size-3" />
      ) : null}
    </button>
  )
}

export { Checkbox }
