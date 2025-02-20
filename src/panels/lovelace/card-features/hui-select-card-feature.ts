import type { HassEntity } from "home-assistant-js-websocket";
import type { PropertyValues } from "lit";
import { html, LitElement, nothing } from "lit";
import { customElement, property, query, state } from "lit/decorators";
import { stopPropagation } from "../../../common/dom/stop_propagation";
import type { HaControlSelectMenu } from "../../../components/ha-control-select-menu";
import type { HomeAssistant } from "../../../types";
import type { LovelaceCardFeature, LovelaceCardFeatureEditor } from "../types";
import { cardFeatureStyles } from "./common/card-feature-styles";
import type { SelectCardFeatureConfig } from "./types";

export const supportsSelect = (_: HassEntity) => true;

@customElement("hui-select-card-feature")
class HuiSelectCardFeature extends LitElement implements LovelaceCardFeature {
  @property({ attribute: false }) public hass?: HomeAssistant;

  @state() private _config?: SelectCardFeatureConfig;

  @state() _currentOption?: string;

  @query("ha-control-select-menu", true)
  private _haSelect!: HaControlSelectMenu;

  static getStubConfig(): SelectCardFeatureConfig {
    return {
      type: "select",
      entity_id: "",
    };
  }

  public static async getConfigElement(): Promise<LovelaceCardFeatureEditor> {
    await import("../editor/config-elements/hui-select-feature-editor");
    return document.createElement("hui-select-card-feature");
  }

  public setConfig(config: SelectCardFeatureConfig): void {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    this._config = config;
  }

  protected updated(changedProps: PropertyValues) {
    super.updated(changedProps);
    if (changedProps.has("hass")) {
      const oldHass = changedProps.get("hass") as HomeAssistant | undefined;
      if (
        this.hass &&
        this.hass.formatEntityAttributeValue !==
          oldHass?.formatEntityAttributeValue
      ) {
        this._haSelect.layoutOptions();
      }
    }
  }

  private async _valueChanged(ev: CustomEvent) {
    const option = (ev.target as any).value as string;

    const oldOption = this.hass!.states[this._config!.entity_id].state;

    if (option === oldOption) return;

    this._currentOption = option;

    try {
      await this._setOption(option);
    } catch (_err) {
      this._currentOption = oldOption;
    }
  }

  private async _setOption(option: string) {
    await this.hass!.callService("select", "select_option", {
      entity_id: this._config!.entity_id,
      option: option,
    });
  }

  protected render() {
    if (!this._config || !this.hass) {
      return nothing;
    }

    // const stateObj = this.stateObj;
    //
    // const options = ["option1", "option2", "option3"];
    //     filterModes(
    //   this.stateObj.attributes.options,
    //   this._config.options
    // );

    const entityState = this.hass.states[this._config.entity_id];

    const options = entityState.attributes.options;

    return html`
      <ha-control-select-menu
        show-arrow
        hide-label
        .label=${this.hass.localize("ui.card.select.option")}
        .value=${entityState.state}
        fixedMenuPosition
        naturalMenuWidth
        @selected=${this._valueChanged}
        @closed=${stopPropagation}
      >
        ${options.map(
          (option) => html`
            <ha-list-item .value=${option}>
              ${this.hass!.formatEntityState(entityState, option)}
            </ha-list-item>
          `
        )}
      </ha-control-select-menu>
    `;
  }

  static get styles() {
    return cardFeatureStyles;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "hui-select-card-feature": HuiSelectCardFeature;
  }
}
