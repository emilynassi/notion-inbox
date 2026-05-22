"use server";

import { Client } from "@notionhq/client";
import type { BlockObjectRequest } from "@notionhq/client/build/src/api-endpoints";

const notion = new Client({ auth: process.env.NOTION_TOKEN });

export async function capture(prevState: string, formData: FormData): Promise<string> {
  const content = (formData.get("content") as string)?.trim();
  const url = (formData.get("url") as string)?.trim() || null;

  if (!content) return "Can't save an empty note.";

  // Use first line as the Notion title, store full content in page body
  const firstLine = content.split("\n")[0].slice(0, 200);
  const hasMoreContent = content !== firstLine;

  const children: BlockObjectRequest[] = [];
  if (hasMoreContent) {
    children.push({
      object: "block",
      type: "paragraph",
      paragraph: { rich_text: [{ type: "text", text: { content: content } }] },
    });
  }
  if (url) {
    children.push({
      object: "block",
      type: "paragraph",
      paragraph: { rich_text: [{ type: "text", text: { content: url, link: { url } } }] },
    });
  }

  await notion.pages.create({
    parent: { database_id: process.env.NOTION_NOTES_DB_ID! },
    properties: {
      Title: { title: [{ text: { content: firstLine } }] },
      Status: { status: { name: "Inbox" } },
    },
    children,
  });

  return "ok";
}
