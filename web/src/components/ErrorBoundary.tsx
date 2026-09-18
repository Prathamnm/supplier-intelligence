import { Component, type ErrorInfo, type ReactNode } from 'react'

/** One broken view must not blank the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('View failed to render', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-xl py-24 text-center">
        <div className="text-lg font-semibold">This view could not be displayed.</div>
        <p className="mt-2 text-sm text-ink-2">{this.state.error.message}</p>
        <button
          type="button"
          onClick={() => {
            window.location.hash = '#/'
            this.setState({ error: null })
          }}
          className="mt-4 text-sm text-accent hover:underline"
        >
          Back to overview
        </button>
      </div>
    )
  }
}
