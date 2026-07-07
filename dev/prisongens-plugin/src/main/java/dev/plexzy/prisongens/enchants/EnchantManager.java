package dev.plexzy.prisongens.enchants;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.enchants.enchants.*;
import org.bukkit.NamespacedKey;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataContainer;
import org.bukkit.persistence.PersistentDataType;

import java.util.HashMap;
import java.util.Map;

/**
 * Registra y gestiona todos los encantamientos personalizados.
 */
public class EnchantManager {

    private final PrisonGens plugin;
    private final Map<String, CustomEnchant> registry = new HashMap<>();

    public EnchantManager(PrisonGens plugin) {
        this.plugin = plugin;
        registerDefaults();
    }

    private void registerDefaults() {
        register(new ExplosionEnchant());
        register(new MegaExplosionEnchant());
        register(new DrillEnchant());
        register(new LaserEnchant());
        register(new TornadoEnchant());
        register(new NukeEnchant());
        register(new MeteorEnchant());
        register(new VolcanoEnchant());
        register(new TsunamiEnchant());
        register(new ChainEnchant());
        register(new CrusherEnchant());
        register(new VoidEnchant());
        register(new ImplodeEnchant());
        register(new CollapseEnchant());
        // Aquí se pueden agregar más...
    }

    public void register(CustomEnchant enchant) {
        registry.put(enchant.getId(), enchant);
    }

    public CustomEnchant getEnchant(String id) {
        return registry.get(id);
    }

    public Map<String, CustomEnchant> getAllEnchants() {
        return registry;
    }

    // ── PDC (Persistent Data Container) para Picos ──────────────────────────

    /**
     * Aplica o sube de nivel un encantamiento en un ítem.
     */
    public void addEnchant(ItemStack item, CustomEnchant enchant, int level) {
        if (item == null || !item.hasItemMeta()) return;
        ItemMeta meta = item.getItemMeta();
        PersistentDataContainer pdc = meta.getPersistentDataContainer();
        
        pdc.set(key("enchant_" + enchant.getId()), PersistentDataType.INTEGER, level);
        item.setItemMeta(meta);
        updateLore(item);
    }

    /**
     * Devuelve el nivel actual de un encantamiento en un ítem (0 si no lo tiene).
     */
    public int getEnchantLevel(ItemStack item, CustomEnchant enchant) {
        if (item == null || !item.hasItemMeta()) return 0;
        PersistentDataContainer pdc = item.getItemMeta().getPersistentDataContainer();
        return pdc.getOrDefault(key("enchant_" + enchant.getId()), PersistentDataType.INTEGER, 0);
    }

    /**
     * Obtiene todos los encantamientos activos en un pico.
     */
    public Map<CustomEnchant, Integer> getActiveEnchants(ItemStack item) {
        Map<CustomEnchant, Integer> active = new HashMap<>();
        if (item == null || !item.hasItemMeta()) return active;
        PersistentDataContainer pdc = item.getItemMeta().getPersistentDataContainer();

        for (CustomEnchant enc : registry.values()) {
            Integer level = pdc.get(key("enchant_" + enc.getId()), PersistentDataType.INTEGER);
            if (level != null && level > 0) {
                active.put(enc, level);
            }
        }
        return active;
    }

    /**
     * Reconstruye el lore del pico basándose en sus encantamientos del PDC.
     */
    public void updateLore(ItemStack item) {
        if (item == null || !item.hasItemMeta()) return;
        ItemMeta meta = item.getItemMeta();
        
        java.util.List<String> lore = new java.util.ArrayList<>();
        lore.add("");
        lore.add("§e§lEncantamientos:");

        Map<CustomEnchant, Integer> active = getActiveEnchants(item);
        if (active.isEmpty()) {
            lore.add("§7(Ninguno)");
        } else {
            for (Map.Entry<CustomEnchant, Integer> entry : active.entrySet()) {
                CustomEnchant enc = entry.getKey();
                int level = entry.getValue();
                lore.add(" §7▪ " + enc.getDisplayName() + " " + toRoman(level));
            }
        }
        lore.add("");
        lore.add("§8Shift + Click Derecho para Mejorar");

        meta.setLore(lore);
        item.setItemMeta(meta);
    }

    private NamespacedKey key(String k) {
        return new NamespacedKey(plugin, k);
    }

    private String toRoman(int num) {
        String[] m = {"", "M", "MM", "MMM"};
        String[] c = {"", "C", "CC", "CCC", "CD", "D", "DC", "DCC", "DCCC", "CM"};
        String[] x = {"", "X", "XX", "XXX", "XL", "L", "LX", "LXX", "LXXX", "XC"};
        String[] i = {"", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"};
        if (num > 3999) return String.valueOf(num);
        return m[num/1000] + c[(num%1000)/100] + x[(num%100)/10] + i[num%10];
    }
}
