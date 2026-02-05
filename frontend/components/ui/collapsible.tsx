"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

const CollapsibleContext = React.createContext<{
    open: boolean
    onOpenChange: (open: boolean) => void
}>({
    open: false,
    onOpenChange: () => { },
})

const Collapsible = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & {
        open?: boolean
        onOpenChange?: (open: boolean) => void
        defaultOpen?: boolean
    }
>(({ className, open, onOpenChange, defaultOpen = false, children, ...props }, ref) => {
    const [isOpen, setIsOpen] = React.useState(defaultOpen)

    const isControlled = open !== undefined
    const currentOpen = isControlled ? open : isOpen
    const handleOpenChange = isControlled ? onOpenChange! : setIsOpen

    return (
        <CollapsibleContext.Provider value={{ open: currentOpen!, onOpenChange: handleOpenChange }}>
            <div
                ref={ref}
                data-state={currentOpen ? "open" : "closed"}
                className={cn(className)}
                {...props}
            >
                {children}
            </div>
        </CollapsibleContext.Provider>
    )
})
Collapsible.displayName = "Collapsible"

const CollapsibleTrigger = React.forwardRef<
    HTMLButtonElement,
    React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }
>(({ className, children, onClick, asChild = false, ...props }, ref) => {
    const { open, onOpenChange } = React.useContext(CollapsibleContext)

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
        onOpenChange(!open)
        onClick?.(e)
    }

    if (asChild && React.isValidElement(children)) {
        return React.cloneElement(children as React.ReactElement, {
            // @ts-ignore
            ref: ref,
            // @ts-ignore
            onClick: (e: any) => {
                handleClick(e)
                // @ts-ignore
                children.props.onClick?.(e)
            },
            "data-state": open ? "open" : "closed",
            // @ts-ignore
            className: cn("group cursor-pointer", className, children.props.className),
            ...props
        })
    }

    return (
        <button
            ref={ref}
            type="button"
            className={cn("group cursor-pointer", className)}
            onClick={handleClick}
            data-state={open ? "open" : "closed"}
            {...props}
        >
            {children}
        </button>
    )
})
CollapsibleTrigger.displayName = "CollapsibleTrigger"

const CollapsibleContent = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => {
    const { open } = React.useContext(CollapsibleContext)

    if (!open) return null

    return (
        <div
            ref={ref}
            className={cn("overflow-hidden", className)}
            data-state={open ? "open" : "closed"}
            {...props}
        >
            {children}
        </div>
    )
})
CollapsibleContent.displayName = "CollapsibleContent"

export { Collapsible, CollapsibleTrigger, CollapsibleContent }
