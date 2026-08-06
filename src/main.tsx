import React from "react"
import ReactDOM from "react-dom/client"
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  Clock3,
  Loader2,
  Inbox,
  MessageSquarePlus,
  Plus,
  RefreshCcw,
  Send,
  Tag,
  Trash2,
  X
} from "lucide-react"
import "./styles.css"

type TicketStatus = "open" | "in_progress" | "resolved" | "closed"
type Priority = "low" | "medium" | "high" | "urgent"
type Toast = {
  id: number
  type: "success" | "error"
  message: string
}

type Ticket = {
  ticket_id: number
  title: string
  description: string | null
  status: TicketStatus
  priority: Priority
  category: string
  created_by: string
  created_at: string
  updated_at: string
  message_count: number
}

type TicketMessage = {
  message_id: number
  ticket_id: number
  message_text: string
  author: string
  created_at: string
}

const statuses: TicketStatus[] = ["open", "in_progress", "resolved", "closed"]
const priorities: Priority[] = ["low", "medium", "high", "urgent"]

const statusLabels: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed"
}

const statusStyles: Record<TicketStatus, string> = {
  open: "bg-blue-50 text-blue-700 ring-blue-700/10",
  in_progress: "bg-amber-50 text-amber-800 ring-amber-700/10",
  resolved: "bg-emerald-50 text-emerald-700 ring-emerald-700/10",
  closed: "bg-gray-100 text-gray-700 ring-gray-600/10"
}

const priorityStyles: Record<Priority, string> = {
  low: "bg-slate-50 text-slate-700 ring-slate-600/10",
  medium: "bg-cyan-50 text-cyan-700 ring-cyan-700/10",
  high: "bg-orange-50 text-orange-700 ring-orange-700/10",
  urgent: "bg-rose-50 text-rose-700 ring-rose-700/10"
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    },
    ...options
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Keep the fallback message when the response is not JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

function classNames(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ")
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value))
}

function Badge({
  children,
  className
}: {
  children: React.ReactNode
  className: string
}) {
  return (
    <span
      className={classNames(
        "inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset",
        className
      )}
    >
      {children}
    </span>
  )
}

function Field({
  label,
  children
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-900">{label}</span>
      <div className="mt-2">{children}</div>
    </label>
  )
}

function App() {
  const [tickets, setTickets] = React.useState<Ticket[]>([])
  const [allTickets, setAllTickets] = React.useState<Ticket[]>([])
  const [selectedTicketId, setSelectedTicketId] = React.useState<number | null>(null)
  const [statusFilter, setStatusFilter] = React.useState<"all" | TicketStatus>("all")
  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [isDeleteOpen, setIsDeleteOpen] = React.useState(false)
  const [initialLoading, setInitialLoading] = React.useState(true)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [messagesLoading, setMessagesLoading] = React.useState(false)
  const [toasts, setToasts] = React.useState<Toast[]>([])

  const [newTicket, setNewTicket] = React.useState({
    title: "",
    description: "",
    created_by: "",
    priority: "medium" as Priority,
    category: "general"
  })
  const [newMessage, setNewMessage] = React.useState({
    author: "",
    message_text: ""
  })
  const [pendingStatus, setPendingStatus] = React.useState<TicketStatus>("open")
  const [messageCache, setMessageCache] = React.useState<
    Record<number, TicketMessage[]>
  >({})
  const hasLoadedTickets = React.useRef(false)

  const selectedTicket =
    tickets.find((ticket) => ticket.ticket_id === selectedTicketId) ?? tickets[0]
  const selectedMessages = selectedTicket
    ? messageCache[selectedTicket.ticket_id] ?? []
    : []

  const stats = React.useMemo(() => {
    return {
      total: allTickets.length,
      open: allTickets.filter((ticket) => ticket.status === "open").length,
      inProgress: allTickets.filter((ticket) => ticket.status === "in_progress").length,
      resolved: allTickets.filter((ticket) => ticket.status === "resolved").length,
      messages: allTickets.reduce((total, ticket) => total + ticket.message_count, 0)
    }
  }, [allTickets])

  const statusChartRows = React.useMemo(
    () =>
      statuses.map((status) => ({
        key: status,
        label: statusLabels[status],
        value: allTickets.filter((ticket) => ticket.status === status).length
      })),
    [allTickets]
  )

  const priorityChartRows = React.useMemo(
    () =>
      priorities.map((priority) => ({
        key: priority,
        label: priority,
        value: allTickets.filter((ticket) => ticket.priority === priority).length
      })),
    [allTickets]
  )

  const maxStatusCount = Math.max(1, ...statusChartRows.map((row) => row.value))
  const maxPriorityCount = Math.max(1, ...priorityChartRows.map((row) => row.value))

  const showToast = React.useCallback((message: string, type: Toast["type"]) => {
    const id = window.Date.now()
    setToasts((current) => [...current, { id, type, message }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 3500)
  }, [])

  const loadTickets = React.useCallback(async (statusOverride?: "all" | TicketStatus) => {
    const activeFilter = statusOverride ?? statusFilter
    if (!hasLoadedTickets.current) {
      setInitialLoading(true)
    } else {
      setIsRefreshing(true)
    }
    const query = activeFilter === "all" ? "" : `?status=${activeFilter}`
    try {
      const loaded = await request<Ticket[]>(`/api/tickets${query}`)
      const fullTicketList =
        activeFilter === "all" ? loaded : await request<Ticket[]>("/api/tickets")
      setTickets(loaded)
      setAllTickets(fullTicketList)
      setSelectedTicketId((current) => {
        if (loaded.length === 0) return null
        if (current === null || !loaded.some((ticket) => ticket.ticket_id === current)) {
          return loaded[0].ticket_id
        }
        return current
      })
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Could not load tickets",
        "error"
      )
    } finally {
      hasLoadedTickets.current = true
      setInitialLoading(false)
      setIsRefreshing(false)
    }
  }, [showToast, statusFilter])

  const loadMessages = React.useCallback(async (ticketId: number) => {
    if (messageCache[ticketId]) return
    setMessagesLoading(true)
    try {
      const loaded = await request<TicketMessage[]>(
        `/api/tickets/${ticketId}/messages`
      )
      setMessageCache((current) => ({ ...current, [ticketId]: loaded }))
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Could not load messages",
        "error"
      )
    } finally {
      setMessagesLoading(false)
    }
  }, [messageCache, showToast])

  React.useEffect(() => {
    void loadTickets()
  }, [loadTickets])

  React.useEffect(() => {
    if (selectedTicket?.ticket_id) {
      setPendingStatus(selectedTicket.status)
      void loadMessages(selectedTicket.ticket_id)
    } else {
      setPendingStatus("open")
    }
  }, [loadMessages, selectedTicket?.ticket_id, selectedTicket?.status])

  async function handleCreateTicket(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!newTicket.title.trim() || !newTicket.created_by.trim()) {
      showToast("Title and Created by are required.", "error")
      return
    }

    try {
      const created = await request<{ ticket_id: number }>("/api/tickets", {
        method: "POST",
        body: JSON.stringify(newTicket)
      })
      setNewTicket({
        title: "",
        description: "",
        created_by: "",
        priority: "medium",
        category: "general"
      })
      setStatusFilter("all")
      await loadTickets("all")
      setSelectedTicketId(created.ticket_id)
      setIsCreateOpen(false)
      showToast(`Created ticket #${created.ticket_id}.`, "success")
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Could not create ticket",
        "error"
      )
    }
  }

  async function handleAddMessage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedTicket) return

    if (!newMessage.author.trim() || !newMessage.message_text.trim()) {
      showToast("Author and Message are required.", "error")
      return
    }

    try {
      await request(`/api/tickets/${selectedTicket.ticket_id}/messages`, {
        method: "POST",
        body: JSON.stringify(newMessage)
      })
      setNewMessage({ author: "", message_text: "" })
      const loaded = await request<TicketMessage[]>(
        `/api/tickets/${selectedTicket.ticket_id}/messages`
      )
      setMessageCache((current) => ({
        ...current,
        [selectedTicket.ticket_id]: loaded
      }))
      await loadTickets()
      showToast("Message added.", "success")
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Could not add message", "error")
    }
  }

  async function handleStatusConfirm() {
    if (!selectedTicket || pendingStatus === selectedTicket.status) return
    try {
      await request(`/api/tickets/${selectedTicket.ticket_id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: pendingStatus })
      })
      await loadTickets()
      showToast("Ticket status updated.", "success")
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Could not update status",
        "error"
      )
    }
  }

  async function handleDelete() {
    if (!selectedTicket) return
    try {
      await request(`/api/tickets/${selectedTicket.ticket_id}`, {
        method: "DELETE"
      })
      setSelectedTicketId(null)
      setIsDeleteOpen(false)
      await loadTickets()
      showToast("Ticket deleted.", "success")
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Could not delete ticket",
        "error"
      )
    }
  }

  return (
    <div className="min-h-full bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <div className="flex items-center gap-x-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <Inbox className="size-5" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-gray-900">
                AI Support Foundation
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                Operational support tickets stored in Lakebase.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center justify-center gap-x-2 rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
          >
            <Plus className="size-4" aria-hidden="true" />
            Create ticket
          </button>
        </div>
      </header>

      {toasts.length > 0 && (
        <div className="fixed right-4 top-4 z-50 w-[calc(100%-2rem)] max-w-sm space-y-3">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={classNames(
                "flex items-start gap-3 rounded-lg bg-white p-4 text-sm shadow-lg ring-1 ring-gray-900/10",
                toast.type === "success" ? "text-emerald-900" : "text-red-900"
              )}
              role="status"
            >
              {toast.type === "success" ? (
                <CheckCircle2
                  className="mt-0.5 size-5 shrink-0 text-emerald-600"
                  aria-hidden="true"
                />
              ) : (
                <AlertCircle
                  className="mt-0.5 size-5 shrink-0 text-red-600"
                  aria-hidden="true"
                />
              )}
              <p className="min-w-0 flex-1 font-medium">{toast.message}</p>
              <button
                type="button"
                className="rounded-md p-1 text-gray-400 hover:bg-gray-50 hover:text-gray-600"
                onClick={() =>
                  setToasts((current) =>
                    current.filter((currentToast) => currentToast.id !== toast.id)
                  )
                }
                aria-label="Dismiss notification"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      )}

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.9fr)]">
          <section className="space-y-6">
            <div className="rounded-lg bg-white shadow-sm ring-1 ring-gray-900/5">
              <div className="border-b border-gray-200 px-4 py-5 sm:px-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-gray-900">Tickets</h2>
                    <p className="mt-1 text-sm text-gray-500">
                      Select a ticket to view messages and status controls.
                    </p>
                  </div>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <select
                      value={statusFilter}
                      onChange={(event) =>
                        setStatusFilter(event.target.value as "all" | TicketStatus)
                      }
                      className="block rounded-md border-0 py-2 pl-3 pr-10 text-gray-900 ring-1 ring-gray-300 ring-inset focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                    >
                      <option value="all">All statuses</option>
                      {statuses.map((status) => (
                        <option key={status} value={status}>
                          {statusLabels[status]}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => void loadTickets()}
                      disabled={isRefreshing}
                      className="inline-flex items-center justify-center gap-x-2 rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {isRefreshing ? (
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <RefreshCcw className="size-4" aria-hidden="true" />
                      )}
                      {isRefreshing ? "Refreshing" : "Refresh"}
                    </button>
                  </div>
                </div>
              </div>

              <div className="relative h-[520px] overflow-hidden">
                {isRefreshing && tickets.length > 0 && (
                  <div className="absolute right-4 top-4 z-10 inline-flex items-center gap-x-2 rounded-md bg-white/95 px-3 py-2 text-xs font-semibold text-gray-600 shadow-sm ring-1 ring-gray-900/10">
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    Syncing
                  </div>
                )}

                {initialLoading ? (
                  <div className="h-full divide-y divide-gray-100 overflow-hidden">
                    {Array.from({ length: 5 }).map((_, index) => (
                      <div key={index} className="px-4 py-5 sm:px-6">
                        <div className="h-4 w-2/3 animate-pulse rounded bg-gray-200" />
                        <div className="mt-3 flex gap-2">
                          <div className="h-6 w-16 animate-pulse rounded-md bg-gray-100" />
                          <div className="h-6 w-20 animate-pulse rounded-md bg-gray-100" />
                          <div className="h-6 w-24 animate-pulse rounded-md bg-gray-100" />
                        </div>
                        <div className="mt-4 h-3 w-full animate-pulse rounded bg-gray-100" />
                        <div className="mt-2 h-3 w-4/5 animate-pulse rounded bg-gray-100" />
                      </div>
                    ))}
                  </div>
                ) : tickets.length === 0 ? (
                  <div className="flex h-full items-center justify-center p-8 text-center">
                    <div>
                      <Inbox
                        className="mx-auto size-10 text-gray-300"
                        aria-hidden="true"
                      />
                      <h3 className="mt-2 text-sm font-semibold text-gray-900">
                        No tickets found
                      </h3>
                      <p className="mt-1 text-sm text-gray-500">
                        Create a ticket or choose a different status filter.
                      </p>
                    </div>
                  </div>
                ) : (
                  <ul role="list" className="h-full divide-y divide-gray-100 overflow-y-auto">
                    {tickets.map((ticket) => (
                      <li key={ticket.ticket_id}>
                        <button
                          type="button"
                          onClick={() => setSelectedTicketId(ticket.ticket_id)}
                          className={classNames(
                            "block w-full px-4 py-5 text-left transition-colors hover:bg-gray-50 sm:px-6",
                            ticket.ticket_id === selectedTicket?.ticket_id &&
                              "bg-indigo-50/60"
                          )}
                        >
                          <div className="flex items-start justify-between gap-x-4">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-gray-900">
                                #{ticket.ticket_id} {ticket.title}
                              </p>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <Badge className={statusStyles[ticket.status]}>
                                  {statusLabels[ticket.status]}
                                </Badge>
                                <Badge className={priorityStyles[ticket.priority]}>
                                  {ticket.priority}
                                </Badge>
                                <span className="inline-flex items-center gap-x-1 text-xs text-gray-500">
                                  <Tag className="size-3" aria-hidden="true" />
                                  {ticket.category}
                                </span>
                              </div>
                            </div>
                            <div className="shrink-0 text-right">
                              <p className="text-xs text-gray-500">
                                {ticket.message_count} messages
                              </p>
                              <p className="mt-1 text-xs text-gray-400">
                                {formatDate(ticket.created_at)}
                              </p>
                            </div>
                          </div>
                          {ticket.description && (
                            <p className="mt-3 line-clamp-2 text-sm text-gray-600">
                              {ticket.description}
                            </p>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-gray-900/5 sm:p-6">
              <div className="flex items-center justify-between gap-x-4">
                <div>
                  <h2 className="text-base font-semibold text-gray-900">Stats</h2>
                  <p className="mt-1 text-sm text-gray-500">
                    Live ticket distribution from Lakebase.
                  </p>
                </div>
                <BarChart3 className="size-5 text-gray-400" aria-hidden="true" />
              </div>

              <dl className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
                {[
                  ["Tickets", stats.total],
                  ["Open", stats.open],
                  ["In progress", stats.inProgress],
                  ["Messages", stats.messages]
                ].map(([label, value]) => (
                  <div key={label} className="rounded-md bg-gray-50 p-3">
                    <dt className="text-xs font-medium text-gray-500">{label}</dt>
                    <dd className="mt-1 text-2xl font-semibold text-gray-900">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>

              <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    Status mix
                  </h3>
                  <div className="mt-4 space-y-3">
                    {statusChartRows.map((row) => (
                      <div key={row.key}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="font-medium text-gray-600">{row.label}</span>
                          <span className="text-gray-500">{row.value}</span>
                        </div>
                        <div className="h-2 rounded-full bg-gray-100">
                          <div
                            className="h-2 rounded-full bg-indigo-600"
                            style={{
                              width: `${Math.max(6, (row.value / maxStatusCount) * 100)}%`
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    Priority mix
                  </h3>
                  <div className="mt-4 flex h-32 items-end gap-3">
                    {priorityChartRows.map((row) => (
                      <div key={row.key} className="flex flex-1 flex-col items-center gap-2">
                        <div className="flex h-24 w-full items-end rounded-md bg-gray-100 px-1">
                          <div
                            className="w-full rounded-t bg-slate-700"
                            style={{
                              height: `${Math.max(8, (row.value / maxPriorityCount) * 100)}%`
                            }}
                          />
                        </div>
                        <div className="text-center text-[11px] font-medium text-gray-500">
                          <span className="block capitalize">{row.label}</span>
                          <span className="text-gray-400">{row.value}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </section>
          </section>

          <section className="rounded-lg bg-white shadow-sm ring-1 ring-gray-900/5">
            {selectedTicket ? (
              <>
                <div className="border-b border-gray-200 px-4 py-5 sm:px-6">
                  <div className="flex items-start justify-between gap-x-4">
                    <div>
                      <h2 className="text-base font-semibold text-gray-900">
                        {selectedTicket.title}
                      </h2>
                      <p className="mt-1 text-sm text-gray-500">
                        Created by {selectedTicket.created_by} on{" "}
                        {formatDate(selectedTicket.created_at)}
                      </p>
                    </div>
                    <Badge className={statusStyles[selectedTicket.status]}>
                      {statusLabels[selectedTicket.status]}
                    </Badge>
                  </div>

                  {selectedTicket.description && (
                    <p className="mt-4 text-sm text-gray-700">
                      {selectedTicket.description}
                    </p>
                  )}

                  <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <Field label="Update status">
                      <div className="flex gap-2">
                        <select
                          value={pendingStatus}
                          onChange={(event) =>
                            setPendingStatus(event.target.value as TicketStatus)
                          }
                          className="block min-w-0 flex-1 rounded-md border-0 py-2 pl-3 pr-10 text-gray-900 ring-1 ring-gray-300 ring-inset focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                        >
                          {statuses.map((status) => (
                            <option key={status} value={status}>
                              {statusLabels[status]}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => void handleStatusConfirm()}
                          disabled={pendingStatus === selectedTicket.status}
                          className="inline-flex shrink-0 items-center justify-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                        >
                          Confirm
                        </button>
                      </div>
                    </Field>
                    <div className="flex flex-col justify-end">
                      <span className="text-sm font-medium text-gray-900">
                        Delete ticket
                      </span>
                      <button
                        type="button"
                        onClick={() => setIsDeleteOpen(true)}
                        className="mt-2 inline-flex w-fit items-center gap-x-2 rounded-md bg-white px-3 py-2 text-sm font-semibold text-red-700 shadow-sm ring-1 ring-red-300 ring-inset hover:bg-red-50"
                      >
                        <Trash2 className="size-4" aria-hidden="true" />
                        Delete ticket
                      </button>
                    </div>
                  </div>
                </div>

                <div className="px-4 py-5 sm:px-6">
                  <div className="flex items-center gap-x-2">
                    <MessageSquarePlus
                      className="size-5 text-gray-400"
                      aria-hidden="true"
                    />
                    <h3 className="text-sm font-semibold text-gray-900">
                      Conversation
                    </h3>
                  </div>

                  <div className="relative mt-5 min-h-[212px]">
                    {messagesLoading && selectedMessages.length > 0 && (
                      <div className="absolute right-0 top-0 z-10 inline-flex items-center gap-x-2 rounded-md bg-white/95 px-3 py-2 text-xs font-semibold text-gray-600 shadow-sm ring-1 ring-gray-900/10">
                        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                        Syncing
                      </div>
                    )}

                    {messagesLoading && selectedMessages.length === 0 ? (
                      <div className="space-y-4">
                        {Array.from({ length: 2 }).map((_, index) => (
                          <div
                            key={index}
                            className="rounded-lg bg-gray-50 p-4 ring-1 ring-gray-900/5"
                          >
                            <div className="h-4 w-5/6 animate-pulse rounded bg-gray-200" />
                            <div className="mt-3 h-3 w-1/3 animate-pulse rounded bg-gray-200" />
                          </div>
                        ))}
                      </div>
                    ) : selectedMessages.length === 0 ? (
                      <div className="rounded-lg bg-gray-50 p-5 text-sm text-gray-500 ring-1 ring-gray-900/5">
                        No messages yet.
                      </div>
                    ) : (
                      <ol className="space-y-4">
                        {selectedMessages.map((message) => (
                          <li
                            key={message.message_id}
                            className="rounded-lg bg-gray-50 p-4 ring-1 ring-gray-900/5"
                          >
                            <p className="text-sm text-gray-800">
                              {message.message_text}
                            </p>
                            <div className="mt-3 flex items-center gap-x-2 text-xs text-gray-500">
                              <Clock3 className="size-3.5" aria-hidden="true" />
                              <span>{message.author}</span>
                              <span aria-hidden="true">/</span>
                              <span>{formatDate(message.created_at)}</span>
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>

                  <form className="mt-6 space-y-4" onSubmit={handleAddMessage}>
                    <Field label="Author">
                      <input
                        value={newMessage.author}
                        onChange={(event) =>
                          setNewMessage((current) => ({
                            ...current,
                            author: event.target.value
                          }))
                        }
                        maxLength={120}
                        className="block w-full rounded-md border-0 px-3 py-2 text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                        placeholder="name@company.com"
                      />
                    </Field>
                    <Field label="Message">
                      <textarea
                        value={newMessage.message_text}
                        onChange={(event) =>
                          setNewMessage((current) => ({
                            ...current,
                            message_text: event.target.value
                          }))
                        }
                        maxLength={500}
                        rows={3}
                        className="block w-full rounded-md border-0 px-3 py-2 text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                        placeholder="Add the next support update..."
                      />
                    </Field>
                    <button
                      type="submit"
                      className="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                    >
                      <Send className="size-4" aria-hidden="true" />
                      Add message
                    </button>
                  </form>
                </div>
              </>
            ) : (
              <div className="p-8 text-center">
                <Inbox className="mx-auto size-10 text-gray-300" aria-hidden="true" />
                <h3 className="mt-2 text-sm font-semibold text-gray-900">
                  No ticket selected
                </h3>
                <p className="mt-1 text-sm text-gray-500">
                  Create a ticket or choose a different status filter.
                </p>
              </div>
            )}
          </section>
        </div>
      </main>

      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-gray-900/40 px-4 py-6 sm:items-center">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-ticket-title"
            className="w-full max-w-2xl rounded-lg bg-white shadow-xl ring-1 ring-gray-900/10"
          >
            <div className="flex items-start justify-between border-b border-gray-200 px-4 py-5 sm:px-6">
              <div>
                <h2
                  id="create-ticket-title"
                  className="text-base font-semibold text-gray-900"
                >
                  Create a new ticket
                </h2>
                <p className="mt-1 text-sm text-gray-500">
                  New records are inserted directly into Lakebase.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                className="rounded-md p-2 text-gray-400 hover:bg-gray-50 hover:text-gray-600"
                aria-label="Close create ticket dialog"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            <form onSubmit={handleCreateTicket} className="space-y-5 px-4 py-5 sm:px-6">
              <Field label="Title">
                <input
                  value={newTicket.title}
                  onChange={(event) =>
                    setNewTicket((current) => ({
                      ...current,
                      title: event.target.value
                    }))
                  }
                  maxLength={120}
                  className="block w-full rounded-md border-0 px-3 py-2 text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                  placeholder="Short description of the issue"
                />
              </Field>

              <Field label="Description">
                <textarea
                  value={newTicket.description}
                  onChange={(event) =>
                    setNewTicket((current) => ({
                      ...current,
                      description: event.target.value
                    }))
                  }
                  maxLength={500}
                  rows={3}
                  className="block w-full rounded-md border-0 px-3 py-2 text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                  placeholder="What happened, who is blocked, and any useful context"
                />
              </Field>

              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field label="Created by">
                  <input
                    value={newTicket.created_by}
                    onChange={(event) =>
                      setNewTicket((current) => ({
                        ...current,
                        created_by: event.target.value
                      }))
                    }
                    maxLength={120}
                    className="block w-full rounded-md border-0 px-3 py-2 text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                    placeholder="name@company.com"
                  />
                </Field>
                <Field label="Category">
                  <input
                    value={newTicket.category}
                    onChange={(event) =>
                      setNewTicket((current) => ({
                        ...current,
                        category: event.target.value
                      }))
                    }
                    maxLength={80}
                    className="block w-full rounded-md border-0 px-3 py-2 text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset placeholder:text-gray-400 focus:ring-2 focus:ring-indigo-600 sm:text-sm"
                  />
                </Field>
              </div>

              <Field label="Priority">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {priorities.map((priority) => (
                    <label
                      key={priority}
                      className={classNames(
                        "flex cursor-pointer items-center justify-center rounded-md px-3 py-2 text-sm font-semibold ring-1 ring-inset",
                        newTicket.priority === priority
                          ? "bg-indigo-600 text-white ring-indigo-600"
                          : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                      )}
                    >
                      <input
                        type="radio"
                        name="priority"
                        value={priority}
                        checked={newTicket.priority === priority}
                        onChange={() =>
                          setNewTicket((current) => ({
                            ...current,
                            priority
                          }))
                        }
                        className="sr-only"
                      />
                      {priority}
                    </label>
                  ))}
                </div>
              </Field>

              <div className="flex justify-end gap-x-3 border-t border-gray-200 pt-5">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                >
                  <Plus className="size-4" aria-hidden="true" />
                  Create ticket
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isDeleteOpen && selectedTicket && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-gray-900/40 px-4 py-6 sm:items-center">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-ticket-title"
            className="w-full max-w-md rounded-lg bg-white shadow-xl ring-1 ring-gray-900/10"
          >
            <div className="flex items-start justify-between border-b border-gray-200 px-4 py-5 sm:px-6">
              <div>
                <h2
                  id="delete-ticket-title"
                  className="text-base font-semibold text-gray-900"
                >
                  Delete ticket?
                </h2>
                <p className="mt-1 text-sm text-gray-500">
                  Ticket #{selectedTicket.ticket_id} and its messages will be removed
                  from Lakebase.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsDeleteOpen(false)}
                className="rounded-md p-2 text-gray-400 hover:bg-gray-50 hover:text-gray-600"
                aria-label="Close delete ticket dialog"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            <div className="px-4 py-5 sm:px-6">
              <p className="text-sm font-medium text-gray-900">
                {selectedTicket.title}
              </p>
              <p className="mt-2 text-sm text-gray-500">
                This action cannot be undone.
              </p>
            </div>

            <div className="flex justify-end gap-x-3 border-t border-gray-200 px-4 py-4 sm:px-6">
              <button
                type="button"
                onClick={() => setIsDeleteOpen(false)}
                className="rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-gray-300 ring-inset hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                className="inline-flex items-center gap-x-2 rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-500"
              >
                <Trash2 className="size-4" aria-hidden="true" />
                Delete ticket
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
