import { html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators";
import { fireEvent } from "../../../../common/dom/fire_event";
import "../../../../components/ha-form/ha-form";
import type {
  HaFormSchema,
  SchemaUnion,
} from "../../../../components/ha-form/types";
import type { HomeAssistant } from "../../../../types";
import type {
  LovelaceCardFeatureContext,
  SelectCardFeatureConfig,
} from "../../card-features/types";
import type { LovelaceCardFeatureEditor } from "../../types";

@customElement("hui-select-feature-editor")
export class HuiSelectFeatureEditor
  extends LitElement
  implements LovelaceCardFeatureEditor
{
  @property({ attribute: false }) public hass?: HomeAssistant;

  @property({ attribute: false }) public context?: LovelaceCardFeatureContext;

  @state() private _config?: SelectCardFeatureConfig;

  public setConfig(config: SelectCardFeatureConfig): void {
    this._config = config;
  }

  private _schema = () =>
    [
      {
        name: "entity_id",
        selector: {
          entity: { domain: "select" },
        },
      },
    ] as const satisfies readonly HaFormSchema[];

  protected render() {
    if (!this.hass || !this._config) {
      return nothing;
    }

    const schema = [
      {
        name: "entity_id",
        selector: {
          entity: { domain: "select" },
        },
      },
    ] as const satisfies readonly HaFormSchema[];

    return html`
      <ha-form
        .hass=${this.hass}
        .data=${this._config}
        .schema=${schema}
        .computeLabel=${this._computeLabelCallback}
        @value-changed=${this._valueChanged}
      ></ha-form>
    `;
  }

  private _valueChanged(ev: CustomEvent): void {
    const { ...config } = ev.detail.value as SelectCardFeatureConfig;

    fireEvent(this, "config-changed", { config: config });
  }

  private _computeLabelCallback = (
    schema: SchemaUnion<ReturnType<typeof this._schema>>
  ) => {
    switch (schema.name) {
      case "entity_id":
        return "Entity";
      default:
        return "";
    }
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "hui-select-feature-editor": HuiSelectFeatureEditor;
  }
}
