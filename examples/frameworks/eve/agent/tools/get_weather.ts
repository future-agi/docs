import { defineTool } from "eve/tools";
import { z } from "zod";

export default defineTool({
  description: "Get the current weather for a city.",
  inputSchema: z.object({ city: z.string().min(1) }),
  async execute({ city }) {
    // "Atlantis" is the example's failure case: the tool throws, so the trace
    // shows an execute_tool span with status ERROR.
    if (city.toLowerCase().includes("atlantis")) {
      throw new Error(`weather service unavailable for ${city}`);
    }
    return { city, condition: "Sunny", temperatureF: 72 };
  },
});
