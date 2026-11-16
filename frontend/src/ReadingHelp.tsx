const terms = {
  map: [
    "Slope from space",
    "Ground slope calculated from a terrain model built using spacecraft images. It describes an area; rover tilt is measured at one place.",
  ],
  cell: [
    "Terrain cell",
    "One small area of the map. Its readings summarize that area; they do not describe every rock or step inside it.",
  ],
  height: [
    "Elevation",
    "Ground height compared with a reference surface on Mars. A negative height means below that reference, not underground.",
  ],
  return: [
    "Distance from start",
    "How far a position is from where the walk begins. This is not the length of a checked, walkable return path.",
  ],
  effort: [
    "Body energy use",
    "An estimate of how hard the body works while walking. W means watts: energy used each second.",
  ],
  oxygen: [
    "Oxygen time left",
    "Estimated oxygen time remaining after the modeled return and other assumed use. It is not a live oxygen-tank reading.",
  ],
  dust: [
    "Dust level",
    "Optical depth describes how much dust blocks light. A higher number means more dust. It is not temperature or a percentage.",
  ],
  weight: [
    "Extra carried weight",
    "Additional equipment carried beyond the body and spacesuit already assumed by the model.",
  ],
  radio: [
    "Radio link margin",
    "The amount of signal weakening the model allows before marking the radio link NO_GO. dB is the unit used to compare signal levels.",
  ],
  solar: [
    "Solar particle burst",
    "A burst of high-energy particles from the Sun. Turning this on makes the model block the walk; terrain shelter does not cancel it.",
  ],
  side: [
    "Sideways slope",
    "Ground that tilts sideways relative to the walking direction, rather than uphill or downhill along the path.",
  ],
  camera: [
    "Camera direction",
    "The angle showing where the camera points around the horizon. The zero direction comes from the camera data; it is not assumed to be north here.",
  ],
} as const;
export default function ReadingHelp({
  topics,
  title = "What do these readings mean?",
}: {
  topics: (keyof typeof terms)[];
  title?: string;
}) {
  return (
    <details className="reading-help">
      <summary>{title}</summary>
      <dl>
        {topics.map((topic) => (
          <div key={topic}>
            <dt>{terms[topic][0]}</dt>
            <dd>{terms[topic][1]}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
