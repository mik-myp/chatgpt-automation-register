import { useState } from "react"
import { CircleHelp, Play } from "lucide-react"
import { useNavigate } from "react-router"

import {
  PRODUCT_TOUR_META,
  TOUR_IDS,
  type ProductTourId,
} from "@/lib/product-tours"
import { Button } from "@workspace/ui/components/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@workspace/ui/components/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"
import { TourAlertDialog, useTour } from "@workspace/ui/components/tour"

const WELCOME_KEY = "gpt-auto-register:tour-welcome-seen"

function waitForTourTarget(selectorId: string) {
  return new Promise<void>((resolve) => {
    let attempts = 0
    const findTarget = () => {
      attempts += 1
      if (document.getElementById(selectorId) || attempts >= 120) {
        resolve()
        return
      }
      requestAnimationFrame(findTarget)
    }
    findTarget()
  })
}

export function ProductTourMenu() {
  const navigate = useNavigate()
  const { isActive, startTour } = useTour()
  const [welcomeOpen, setWelcomeOpen] = useState(
    () => localStorage.getItem(WELCOME_KEY) !== "1"
  )

  const changeWelcomeOpen = (open: boolean) => {
    setWelcomeOpen(open)
    if (!open) localStorage.setItem(WELCOME_KEY, "1")
  }

  const launchTour = async (tourId: ProductTourId) => {
    const tour = PRODUCT_TOUR_META.find((candidate) => candidate.id === tourId)
    if (!tour) return
    changeWelcomeOpen(false)
    navigate(tour.route)

    if (
      tourId === "quick-start" &&
      window.matchMedia("(max-width: 767px)").matches
    ) {
      requestAnimationFrame(() => {
        const trigger = document.querySelector<HTMLButtonElement>(
          '[data-sidebar="trigger"]'
        )
        trigger?.click()
      })
    }

    await waitForTourTarget(tour.firstSelectorId)
    startTour(tourId)
  }

  return (
    <>
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="打开产品导览"
                disabled={isActive}
                id={TOUR_IDS.tourMenu}
                size="icon-sm"
                variant="ghost"
              >
                <CircleHelp />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent>产品导览</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>选择导览</DropdownMenuLabel>
          <DropdownMenuGroup>
            {PRODUCT_TOUR_META.map((tour) => (
              <DropdownMenuItem
                key={tour.id}
                onSelect={() => void launchTour(tour.id)}
              >
                <Play />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span>{tour.label}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {tour.description}
                  </span>
                </span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <TourAlertDialog
        onOpenChange={changeWelcomeOpen}
        onStart={() => void launchTour("quick-start")}
        open={welcomeOpen}
      />
    </>
  )
}
