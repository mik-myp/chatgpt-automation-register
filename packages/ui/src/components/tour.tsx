import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { X } from "lucide-react"

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./alert-dialog"
import { Button } from "./button"
import { cn } from "../lib/utils"

export interface TourStep {
  content: ReactNode
  selectorId: string
  width?: number
  height?: number
  padding?: number
  showSkip?: boolean
  closeable?: boolean
  borderRadius?: number
  position?: "top" | "bottom" | "left" | "right"
}

export interface TourDefinition {
  id: string
  steps: TourStep[]
}

interface TourContextValue {
  activeTourId: string | null
  currentStep: number
  endTour: () => void
  isActive: boolean
  nextStep: () => void
  previousStep: () => void
  startTour: (tourId: string) => void
  steps: TourStep[]
  totalSteps: number
}

interface TourProviderProps {
  children: ReactNode
  tours: TourDefinition[]
  closeable?: boolean
  className?: string
  onStart?: (tourId: string) => void
  onComplete?: (tourId: string) => void
  onSkip?: (tourId: string, step: number) => void
  onStepChange?: (tourId: string, step: number) => void
}

const TourContext = createContext<TourContextValue | null>(null)
const VIEWPORT_PADDING = 16

function getElementPosition(element: HTMLElement) {
  const rect = element.getBoundingClientRect()
  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
  }
}

function calculateContentPosition(
  elementPosition: ReturnType<typeof getElementPosition>,
  position: TourStep["position"] = "bottom",
  contentSize: { width: number; height: number }
) {
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const contentWidth = Math.min(
    contentSize.width,
    viewportWidth - VIEWPORT_PADDING * 2
  )
  const contentHeight = Math.min(
    contentSize.height,
    viewportHeight - VIEWPORT_PADDING * 2
  )
  const alignRight =
    elementPosition.left + elementPosition.width / 2 > viewportWidth / 2
  let left: number
  let top: number

  if (viewportWidth < 640) {
    left = VIEWPORT_PADDING
    const below =
      elementPosition.top + elementPosition.height + VIEWPORT_PADDING
    const above = elementPosition.top - contentHeight - VIEWPORT_PADDING
    top =
      below + contentHeight <= viewportHeight - VIEWPORT_PADDING ? below : above
  } else if (position === "top") {
    top = elementPosition.top - VIEWPORT_PADDING - contentHeight
    left = alignRight
      ? elementPosition.left + elementPosition.width - contentWidth
      : elementPosition.left
  } else if (position === "bottom") {
    top = elementPosition.top + elementPosition.height + VIEWPORT_PADDING
    left = alignRight
      ? elementPosition.left + elementPosition.width - contentWidth
      : elementPosition.left
  } else if (position === "left") {
    left = elementPosition.left - VIEWPORT_PADDING - contentWidth
    top = elementPosition.top + elementPosition.height / 2 - contentHeight / 2
  } else {
    left = elementPosition.left + elementPosition.width + VIEWPORT_PADDING
    top = elementPosition.top + elementPosition.height / 2 - contentHeight / 2
  }

  return {
    top: Math.max(
      VIEWPORT_PADDING,
      Math.min(top, viewportHeight - contentHeight - VIEWPORT_PADDING)
    ),
    left: Math.max(
      VIEWPORT_PADDING,
      Math.min(left, viewportWidth - contentWidth - VIEWPORT_PADDING)
    ),
  }
}

export function TourProvider({
  children,
  tours,
  closeable = true,
  className,
  onStart,
  onComplete,
  onSkip,
  onStepChange,
}: TourProviderProps) {
  const [steps, setSteps] = useState<TourStep[]>([])
  const [currentStep, setCurrentStep] = useState(-1)
  const [activeTourId, setActiveTourId] = useState<string | null>(null)
  const [elementPosition, setElementPosition] = useState<ReturnType<
    typeof getElementPosition
  > | null>(null)
  const [contentSize, setContentSize] = useState({ width: 360, height: 180 })
  const contentRef = useRef<HTMLDivElement>(null)
  const maskId = `tour-mask-${useId().replaceAll(":", "")}`
  const reduceMotion = useReducedMotion()

  const updateElementPosition = useCallback(() => {
    const selectorId = steps[currentStep]?.selectorId
    if (!selectorId) {
      setElementPosition(null)
      return
    }
    const element = document.getElementById(selectorId)
    if (!element) {
      setElementPosition(null)
      return
    }
    const rect = element.getBoundingClientRect()
    if (rect.top < 0 || rect.bottom > window.innerHeight) {
      element.scrollIntoView({
        behavior: reduceMotion ? "auto" : "smooth",
        block: "center",
      })
    }
    setElementPosition(getElementPosition(element))
  }, [currentStep, reduceMotion, steps])

  useEffect(() => {
    if (currentStep < 0) return
    const frame = requestAnimationFrame(updateElementPosition)
    const observer = new MutationObserver(updateElementPosition)
    observer.observe(document.body, { childList: true, subtree: true })
    window.addEventListener("resize", updateElementPosition)
    window.addEventListener("scroll", updateElementPosition, true)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener("resize", updateElementPosition)
      window.removeEventListener("scroll", updateElementPosition, true)
    }
  }, [currentStep, updateElementPosition])

  useLayoutEffect(() => {
    const content = contentRef.current
    if (!content) return
    const updateContentSize = () => {
      const rect = content.getBoundingClientRect()
      setContentSize({ width: rect.width, height: rect.height })
    }
    updateContentSize()
    const observer = new ResizeObserver(updateContentSize)
    observer.observe(content)
    return () => observer.disconnect()
  }, [currentStep])

  const nextStep = useCallback(() => {
    setCurrentStep((previous) => {
      if (previous >= steps.length - 1) {
        if (activeTourId) onComplete?.(activeTourId)
        setActiveTourId(null)
        return -1
      }
      const next = previous + 1
      if (activeTourId) onStepChange?.(activeTourId, next)
      return next
    })
  }, [activeTourId, onComplete, onStepChange, steps.length])

  const previousStep = useCallback(() => {
    setCurrentStep((previous) => {
      const next = Math.max(0, previous - 1)
      if (activeTourId && next !== previous) onStepChange?.(activeTourId, next)
      return next
    })
  }, [activeTourId, onStepChange])

  const endTour = useCallback(() => {
    if (activeTourId) onSkip?.(activeTourId, currentStep)
    setCurrentStep(-1)
    setActiveTourId(null)
  }, [activeTourId, currentStep, onSkip])

  const startTour = useCallback(
    (tourId: string) => {
      const tour = tours.find((candidate) => candidate.id === tourId)
      if (!tour?.steps.length) return
      setElementPosition(null)
      setSteps(tour.steps)
      setActiveTourId(tourId)
      setCurrentStep(0)
      onStart?.(tourId)
    },
    [onStart, tours]
  )

  useEffect(() => {
    if (currentStep < 0) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") nextStep()
      if (event.key === "ArrowLeft") previousStep()
      if (event.key === "Escape") endTour()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [currentStep, endTour, nextStep, previousStep])

  const currentStepData = steps[currentStep]
  const spotlightPadding = currentStepData?.padding ?? 8
  const spotlightBorderRadius = currentStepData?.borderRadius ?? 8
  const spotlightWidth = currentStepData?.width ?? elementPosition?.width ?? 0
  const spotlightHeight =
    currentStepData?.height ?? elementPosition?.height ?? 0
  const contentPosition = useMemo(
    () =>
      elementPosition
        ? calculateContentPosition(
            elementPosition,
            currentStepData?.position,
            contentSize
          )
        : { top: 0, left: 0 },
    [contentSize, currentStepData?.position, elementPosition]
  )
  const isLastStep = currentStep === steps.length - 1
  const showSkip = !isLastStep && currentStepData?.showSkip !== false
  const isCloseable = currentStepData?.closeable ?? closeable
  const transition = reduceMotion ? { duration: 0 } : { duration: 0.2 }

  return (
    <TourContext.Provider
      value={{
        activeTourId,
        currentStep,
        endTour,
        isActive: currentStep >= 0,
        nextStep,
        previousStep,
        startTour,
        steps,
        totalSteps: steps.length,
      }}
    >
      {children}
      <AnimatePresence>
        {currentStep >= 0 && elementPosition && (
          <>
            <motion.svg
              animate={{ opacity: 1 }}
              aria-hidden="true"
              className="pointer-events-auto fixed inset-0 z-[80] size-full"
              exit={{ opacity: 0 }}
              initial={{ opacity: 0 }}
              transition={transition}
            >
              <defs>
                <mask id={maskId}>
                  <rect fill="white" height="100%" width="100%" />
                  <rect
                    fill="black"
                    height={spotlightHeight + spotlightPadding * 2}
                    rx={spotlightBorderRadius}
                    ry={spotlightBorderRadius}
                    width={spotlightWidth + spotlightPadding * 2}
                    x={elementPosition.left - spotlightPadding}
                    y={elementPosition.top - spotlightPadding}
                  />
                </mask>
              </defs>
              <rect
                fill="rgba(0, 0, 0, 0.55)"
                height="100%"
                mask={`url(#${maskId})`}
                width="100%"
              />
            </motion.svg>
            <motion.div
              animate={{ opacity: 1, scale: 1 }}
              aria-hidden="true"
              className={cn(
                "pointer-events-none fixed z-[81] border-2 border-primary shadow-[0_0_0_1px_var(--background)]",
                className
              )}
              exit={{ opacity: 0, scale: 0.98 }}
              initial={{ opacity: 0, scale: 0.98 }}
              style={{
                borderRadius: spotlightBorderRadius,
                height: spotlightHeight,
                left: elementPosition.left,
                top: elementPosition.top,
                width: spotlightWidth,
              }}
              transition={transition}
            />
            <motion.div
              animate={{
                left: contentPosition.left,
                opacity: 1,
                top: contentPosition.top,
                y: 0,
              }}
              aria-label="产品导览"
              aria-modal="true"
              className="fixed z-[82] flex max-h-[calc(100svh-2rem)] w-[calc(100vw-2rem)] max-w-sm flex-col overflow-hidden rounded-lg border bg-popover p-4 text-popover-foreground shadow-lg"
              exit={{ opacity: 0, y: 6 }}
              initial={{ opacity: 0, y: 6 }}
              ref={contentRef}
              role="dialog"
              transition={transition}
            >
              <div className="flex shrink-0 items-start justify-between gap-4">
                <span className="text-xs text-muted-foreground">
                  {currentStep + 1} / {steps.length}
                </span>
                {isCloseable && (
                  <Button
                    aria-label="关闭导览"
                    onClick={endTour}
                    size="icon-xs"
                    variant="ghost"
                  >
                    <X />
                  </Button>
                )}
              </div>
              <AnimatePresence mode="wait">
                <motion.div
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  initial={{ opacity: 0, y: 4 }}
                  key={`${activeTourId}-${currentStep}`}
                  className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1"
                  transition={transition}
                >
                  {currentStepData?.content}
                </motion.div>
              </AnimatePresence>
              <div className="mt-4 flex shrink-0 flex-wrap items-center justify-between gap-3">
                {showSkip ? (
                  <Button onClick={endTour} size="sm" variant="ghost">
                    跳过导览
                  </Button>
                ) : (
                  <span />
                )}
                <div className="flex flex-wrap items-center gap-2">
                  {currentStep > 0 && (
                    <Button onClick={previousStep} size="sm" variant="outline">
                      上一步
                    </Button>
                  )}
                  <Button onClick={nextStep} size="sm">
                    {isLastStep ? "完成" : "下一步"}
                  </Button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </TourContext.Provider>
  )
}

export function useTour() {
  const context = useContext(TourContext)
  if (!context) throw new Error("useTour 必须在 TourProvider 内使用")
  return context
}

export function TourAlertDialog({
  open,
  onOpenChange,
  onStart,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStart: () => void
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>快速了解注册工作流</AlertDialogTitle>
          <AlertDialogDescription>
            用一分钟认识资源准备、流水线执行和结果交付。导览不会修改任何数据。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="ghost">
            稍后再看
          </Button>
          <Button onClick={onStart}>开始导览</Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
