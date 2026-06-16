import React from "react";
import ReactDOM from "react-dom/client";
import CommandCenter from "./cc/CommandCenter";
import "./cc/theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CommandCenter />
  </React.StrictMode>,
);
