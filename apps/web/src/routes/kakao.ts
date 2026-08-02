import { redirect } from "react-router"

export function loader() {
  return redirect("/pipelines")
}

export function Component() {
  return null
}
