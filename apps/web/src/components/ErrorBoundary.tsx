import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorState } from './ErrorState'

type Props = { children: ReactNode; title?: string }
type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('render boundary', { error: error.message, componentStack: info.componentStack })
  }

  render() {
    return this.state.error ? <ErrorState title={this.props.title ?? 'View unavailable'} error={this.state.error} /> : this.props.children
  }
}

export function WidgetBoundary({ children, title }: Props) {
  return <ErrorBoundary title={title}>{children}</ErrorBoundary>
}
