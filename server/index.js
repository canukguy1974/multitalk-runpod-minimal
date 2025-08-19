// /server/index.js  (excerpt)
import express from "express";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";
import { talkingReplyMiddleware, talkingReplyHandler } from "./routes/talking-reply.js";

dotenv.config();

const app = express();
const __dirname = path.dirname(fileURLToPath(import.meta.url));
app.use("/uploads", express.static(path.join(__dirname, "uploads"))); // /server/uploads

app.post("/api/talking-reply", talkingReplyMiddleware, talkingReplyHandler);

app.listen(5050, () => console.log("Server on http://localhost:5050"));
