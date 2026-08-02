import type { MouseEvent } from "react"

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@workspace/ui/components/pagination"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"

function pageWindow(page: number, pageCount: number): Array<number | null> {
  if (pageCount <= 7)
    return Array.from({ length: pageCount }, (_, index) => index)
  const values = new Set([0, pageCount - 1, page - 1, page, page + 1])
  const pages = [...values]
    .filter((value) => value >= 0 && value < pageCount)
    .sort((a, b) => a - b)
  const result: Array<number | null> = []
  for (const value of pages) {
    const previous = result.at(-1)
    if (typeof previous === "number" && value - previous > 1) result.push(null)
    result.push(value)
  }
  return result
}

export function TablePagination({
  page,
  pageCount,
  onPageChange,
  pageSize,
  onPageSizeChange,
  total,
}: {
  page: number
  pageCount: number
  onPageChange: (page: number) => void
  pageSize?: number
  onPageSizeChange?: (size: number) => void
  total?: number
}) {
  const navigate =
    (target: number) => (event: MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault()
      if (target >= 0 && target < pageCount && target !== page)
        onPageChange(target)
    }

  return (
    <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-3">
      {total != null && (
        <span className="text-xs text-muted-foreground">
          总计 {total} 条数据
        </span>
      )}
      {pageSize && onPageSizeChange && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>每页</span>
          <Select
            value={String(pageSize)}
            onValueChange={(value) => onPageSizeChange(Number(value))}
          >
            <SelectTrigger aria-label="每页条数" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[25, 50, 100, 200].map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <Pagination className="mx-0 w-auto justify-end">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              aria-disabled={page === 0}
              className={page === 0 ? "pointer-events-none opacity-50" : ""}
              href="#"
              onClick={navigate(page - 1)}
              text="上一页"
            />
          </PaginationItem>
          {pageWindow(page, pageCount).map((value, index) =>
            value === null ? (
              <PaginationItem key={`ellipsis-${index}`}>
                <PaginationEllipsis />
              </PaginationItem>
            ) : (
              <PaginationItem key={value}>
                <PaginationLink
                  aria-label={`第 ${value + 1} 页`}
                  href="#"
                  isActive={value === page}
                  onClick={navigate(value)}
                  size="icon-sm"
                >
                  {value + 1}
                </PaginationLink>
              </PaginationItem>
            )
          )}
          <PaginationItem>
            <PaginationNext
              aria-disabled={page + 1 >= pageCount}
              className={
                page + 1 >= pageCount ? "pointer-events-none opacity-50" : ""
              }
              href="#"
              onClick={navigate(page + 1)}
              text="下一页"
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  )
}
